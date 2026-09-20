"""Registration, login, refresh, logout, and session/device management.

Per docs/API_CONTRACT.md, `/api/v1/auth` is one of the two namespaces
(alongside `/api/v1/health`) that never requires a session to reach it —
except the session-listing/revocation endpoints, which obviously require an
authenticated caller.

Tokens are delivered as HttpOnly cookies (`app/core/cookies.py`), never in
a JSON response body — see ADR 0005. `refresh`/`logout` read the refresh
token from its cookie, not a request body.
"""

from __future__ import annotations

import uuid

import redis
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.abuse_decision import (
    AbuseContext,
    AbuseRecordOutcome,
    record_forgot_password_request,
    record_login_failure,
    record_login_success,
    record_reset_validation_failure,
)
from app.core.abuse_state import TEMPORARY_BLOCK_TTL_SECONDS
from app.core.audit import AuditEvent
from app.core.audit import record as record_audit_event
from app.core.config import get_settings
from app.core.cookies import REFRESH_TOKEN_COOKIE, clear_auth_cookies, set_auth_cookies
from app.core.db import get_db
from app.core.dependencies import get_current_token_claims, get_current_user
from app.core.ip_resolution import resolve_client_ip
from app.core.rate_limit import (
    client_ip,
    enforce_forgot_password_rate_limit,
    enforce_login_rate_limit,
    enforce_refresh_rate_limit,
    enforce_register_rate_limit,
    enforce_reset_password_rate_limit,
)
from app.core.redis_client import get_redis_client
from app.core.redis_keys import hash_account_identifier
from app.core.security import AccessTokenClaims
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SessionRead,
)
from app.services import auth_service, password_reset_service

_RESET_VALIDATION_FAILURE_CODES = frozenset(
    {"reset_token_invalid", "reset_token_expired", "reset_token_already_used"}
)

router = APIRouter(prefix="/auth", tags=["auth"])

_DEVICE_LABEL_MAX_LENGTH = 255


def _device_label(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    if not user_agent:
        return None
    return user_agent[:_DEVICE_LABEL_MAX_LENGTH]


def _audit_abuse_escalation(
    db: Session, *, context: AbuseContext, outcome: AbuseRecordOutcome
) -> None:
    """Emits exactly one audit row on the transition into STRICT_THROTTLE
    or TEMPORARY_BLOCK (ADR 0006 §11/§12/§15, Slice 3c) — never on an
    already-escalated repeat (`outcome.newly_escalated` is only True on
    the exact call that crossed the threshold; see its own docstring in
    `abuse_decision.py`), and never for an ordinary ALLOW or an ordinary
    base-bucket THROTTLE, since this function is only ever called with
    the result of a `record_*` call, which itself is only reached after
    a real login/forgot-password/reset-password outcome is known.

    `user_id` is deliberately always `None` here: none of the three
    call sites below have a resolved user at this point (a failed login
    never returns one; forgot-password/reset-password never expose one
    to this layer) — never invented. `ip_address` is `context.ip`, the
    same trusted-proxy-resolved value the abuse decision itself acted
    on (not `client_ip()`, which is a different, unconditional value
    used elsewhere for session/authorization audit rows — see
    `app/core/ip_resolution.py`'s module docstring for that distinction).
    """
    if not outcome.newly_escalated:
        return

    event_type = (
        AuditEvent.RATE_LIMITED
        if outcome.action == "STRICT_THROTTLE"
        else AuditEvent.ABUSE_TEMPORARY_BLOCK_APPLIED
    )
    metadata: dict[str, object] = {
        "rule": outcome.rule_id,
        "operation": outcome.operation,
        "dimension": outcome.dimension,
    }
    # The account dimension's value is already an HMAC identifier, never
    # a raw email (see AbuseContext's own docstring) — safe to record.
    # The IP dimension's value is already the audit row's own
    # `ip_address` column; not duplicated into metadata.
    if outcome.dimension == "acct" and context.account_hash is not None:
        metadata["account_hash"] = context.account_hash
    if outcome.action == "TEMPORARY_BLOCK":
        metadata["block_ttl_seconds"] = TEMPORARY_BLOCK_TTL_SECONDS

    record_audit_event(
        db,
        event_type=event_type,
        user_id=None,
        ip_address=context.ip,
        metadata=metadata,
    )


@router.get("/csrf", status_code=status.HTTP_204_NO_CONTENT)
def get_csrf_cookie() -> None:
    """Frontend calls this before rendering login/register so a CSRF
    cookie exists to protect those very requests (CSRFMiddleware sets it
    on any response that doesn't already have one — this endpoint just
    makes that bootstrap step explicit and discoverable)."""
    return None


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_register_rate_limit)],
)
def register(
    request: Request, response: Response, body: RegisterRequest, db: Session = Depends(get_db)
) -> AuthResponse:
    tokens = auth_service.register(
        db,
        email=body.email,
        password=body.password,
        device_label=_device_label(request),
        ip_address=client_ip(request),
    )
    set_auth_cookies(
        response,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        access_max_age_seconds=tokens.access_expires_in,
        refresh_max_age_seconds=tokens.refresh_expires_in,
    )
    return AuthResponse(user=tokens.user)


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
)
def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Session = Depends(get_db),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> AuthResponse:
    settings = get_settings()
    abuse_context = AbuseContext(
        operation="login",
        ip=resolve_client_ip(request, settings.trusted_proxy_cidrs_list),
        account_hash=hash_account_identifier(
            body.email, key=settings.rate_limit_hash_key_resolved.encode("utf-8")
        ),
    )

    # Abuse-layer recording (ADR 0006 §11/§12, Slice 3b) happens only
    # here, after auth_service.login()'s real outcome is known -- never
    # in the pre-request enforce_login_rate_limit dependency, which
    # necessarily runs before authentication is even attempted.
    try:
        tokens = auth_service.login(
            db,
            email=body.email,
            password=body.password,
            device_label=_device_label(request),
            ip_address=client_ip(request),
        )
    except HTTPException:
        outcome = record_login_failure(redis_client, abuse_context)
        _audit_abuse_escalation(db, context=abuse_context, outcome=outcome)
        raise

    record_login_success(redis_client, abuse_context)
    set_auth_cookies(
        response,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        access_max_age_seconds=tokens.access_expires_in,
        refresh_max_age_seconds=tokens.refresh_expires_in,
    )
    return AuthResponse(user=tokens.user)


@router.post(
    "/refresh",
    response_model=AuthResponse,
    dependencies=[Depends(enforce_refresh_rate_limit)],
)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)) -> AuthResponse:
    raw_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if raw_refresh_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    tokens = auth_service.refresh(
        db, raw_refresh_token=raw_refresh_token, ip_address=client_ip(request)
    )
    set_auth_cookies(
        response,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        access_max_age_seconds=tokens.access_expires_in,
        refresh_max_age_seconds=tokens.refresh_expires_in,
    )
    return AuthResponse(user=tokens.user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    raw_refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if raw_refresh_token is not None:
        auth_service.logout(db, raw_refresh_token=raw_refresh_token, ip_address=client_ip(request))
    clear_auth_cookies(response)


_GENERIC_FORGOT_PASSWORD_MESSAGE = (
    "If an account with that email exists, password reset instructions have been sent."
)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(enforce_forgot_password_rate_limit)],
)
def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> MessageResponse:
    settings = get_settings()
    password_reset_service.request_password_reset(
        db, email=body.email, ip_address=client_ip(request)
    )
    # R4 (ADR 0006 §11) counts *requests*, not failures -- recorded
    # unconditionally, since this endpoint has no success/failure branch
    # to key off (see password_reset_service's module docstring).
    abuse_context = AbuseContext(
        operation="forgot-password",
        ip=resolve_client_ip(request, settings.trusted_proxy_cidrs_list),
        account_hash=hash_account_identifier(
            body.email, key=settings.rate_limit_hash_key_resolved.encode("utf-8")
        ),
    )
    outcome = record_forgot_password_request(redis_client, abuse_context)
    _audit_abuse_escalation(db, context=abuse_context, outcome=outcome)
    # Always the same response, same status code, regardless of whether
    # the email exists — see password_reset_service's module docstring.
    return MessageResponse(message=_GENERIC_FORGOT_PASSWORD_MESSAGE)


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_reset_password_rate_limit)],
)
def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
    redis_client: redis.Redis | None = Depends(get_redis_client),
) -> None:
    settings = get_settings()
    abuse_context = AbuseContext(
        operation="reset-password",
        ip=resolve_client_ip(request, settings.trusted_proxy_cidrs_list),
    )
    try:
        password_reset_service.reset_password(
            db,
            raw_token=body.token,
            new_password=body.new_password,
            ip_address=client_ip(request),
        )
    except HTTPException as exc:
        # R5 (ADR 0006 §11) counts validation failures only -- a
        # successful reset never reaches this branch, so it never
        # records anything here.
        detail = exc.detail
        code = detail.get("code") if isinstance(detail, dict) else None
        if code in _RESET_VALIDATION_FAILURE_CODES:
            outcome = record_reset_validation_failure(redis_client, abuse_context)
            _audit_abuse_escalation(db, context=abuse_context, outcome=outcome)
        raise


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(
    user: User = Depends(get_current_user),
    claims: AccessTokenClaims = Depends(get_current_token_claims),
    db: Session = Depends(get_db),
) -> list[SessionRead]:
    return auth_service.list_sessions(db, user_id=user.id, current_session_id=claims.session_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    request: Request,
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    auth_service.revoke_session(
        db, user_id=user.id, session_id=session_id, ip_address=client_ip(request)
    )
