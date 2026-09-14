from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import csrf_headers

_PASSWORD = "correct horse battery staple"


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def _register(client: TestClient, email: str | None = None) -> dict[str, Any]:
    email = email or _unique_email()
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": _PASSWORD},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _create_workspace(client: TestClient, name: str = "Acme") -> dict[str, Any]:
    response = client.post(
        "/api/v1/workspaces", json={"name": name}, headers=csrf_headers(client)
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def _add_member(client: TestClient, workspace_id: str, email: str, role: str) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": email, "role": role},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def test_create_workspace_makes_creator_owner(client: TestClient) -> None:
    _register(client)

    workspace = _create_workspace(client)

    assert workspace["name"] == "Acme"
    assert workspace["my_role"] == "OWNER"


def test_list_workspaces_returns_only_memberships(client_factory: Callable[[], TestClient]) -> None:
    client_a = client_factory()
    client_b = client_factory()
    _register(client_a)
    _register(client_b)
    _create_workspace(client_a, "A's workspace")
    _create_workspace(client_b, "B's workspace")

    response = client_a.get("/api/v1/workspaces")

    assert response.status_code == 200
    names = {w["name"] for w in response.json()}
    assert names == {"A's workspace"}


def test_get_workspace_requires_authentication(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    _register(owner)
    workspace = _create_workspace(owner)
    anonymous = client_factory()

    response = anonymous.get(f"/api/v1/workspaces/{workspace['id']}")

    assert response.status_code == 401


def test_update_workspace_name_by_owner(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    response = client.patch(
        f"/api/v1/workspaces/{workspace['id']}",
        json={"name": "New Name"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_delete_workspace_by_owner(client: TestClient) -> None:
    _register(client)
    workspace = _create_workspace(client)

    response = client.delete(
        f"/api/v1/workspaces/{workspace['id']}", headers=csrf_headers(client)
    )

    assert response.status_code == 204
    assert client.get(f"/api/v1/workspaces/{workspace['id']}").status_code == 404


def test_owner_can_add_member(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    member = client_factory()
    _register(owner)
    member_body = _register(member)
    workspace = _create_workspace(owner)

    added = _add_member(owner, workspace["id"], member_body["user"]["email"], "MEMBER")

    assert added["role"] == "MEMBER"
    assert added["email"] == member_body["user"]["email"]


def test_plain_member_cannot_add_members(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    member = client_factory()
    _register(owner)
    member_body = _register(member)
    workspace = _create_workspace(owner)
    _add_member(owner, workspace["id"], member_body["user"]["email"], "MEMBER")

    response = member.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": _unique_email(), "role": "MEMBER"},
        headers=csrf_headers(member),
    )

    assert response.status_code == 403


def test_admin_cannot_assign_owner_role(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    admin = client_factory()
    _register(owner)
    admin_body = _register(admin)
    workspace = _create_workspace(owner)
    _add_member(owner, workspace["id"], admin_body["user"]["email"], "ADMIN")

    response = admin.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": _unique_email(), "role": "OWNER"},
        headers=csrf_headers(admin),
    )

    assert response.status_code == 403


def test_admin_can_assign_member_and_viewer_roles(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    admin = client_factory()
    viewer = client_factory()
    _register(owner)
    admin_body = _register(admin)
    viewer_body = _register(viewer)
    workspace = _create_workspace(owner)
    _add_member(owner, workspace["id"], admin_body["user"]["email"], "ADMIN")

    added = _add_member(admin, workspace["id"], viewer_body["user"]["email"], "VIEWER")

    assert added["role"] == "VIEWER"


def test_owner_can_promote_member_to_admin(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    member = client_factory()
    _register(owner)
    member_body = _register(member)
    workspace = _create_workspace(owner)
    _add_member(owner, workspace["id"], member_body["user"]["email"], "MEMBER")

    response = owner.patch(
        f"/api/v1/workspaces/{workspace['id']}/members/{member_body['user']['id']}",
        json={"role": "ADMIN"},
        headers=csrf_headers(owner),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"


def test_admin_cannot_change_another_admins_role(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    admin_one = client_factory()
    admin_two = client_factory()
    _register(owner)
    admin_one_body = _register(admin_one)
    admin_two_body = _register(admin_two)
    workspace = _create_workspace(owner)
    _add_member(owner, workspace["id"], admin_one_body["user"]["email"], "ADMIN")
    _add_member(owner, workspace["id"], admin_two_body["user"]["email"], "ADMIN")

    response = admin_one.patch(
        f"/api/v1/workspaces/{workspace['id']}/members/{admin_two_body['user']['id']}",
        json={"role": "VIEWER"},
        headers=csrf_headers(admin_one),
    )

    assert response.status_code == 403


def test_cannot_demote_the_last_owner(client: TestClient) -> None:
    owner_body = _register(client)
    workspace = _create_workspace(client)

    response = client.patch(
        f"/api/v1/workspaces/{workspace['id']}/members/{owner_body['user']['id']}",
        json={"role": "ADMIN"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 409


def test_member_can_leave_workspace(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    member = client_factory()
    _register(owner)
    member_body = _register(member)
    workspace = _create_workspace(owner)
    _add_member(owner, workspace["id"], member_body["user"]["email"], "MEMBER")

    response = member.delete(
        f"/api/v1/workspaces/{workspace['id']}/members/{member_body['user']['id']}",
        headers=csrf_headers(member),
    )

    assert response.status_code == 204
    still_visible = member.get(f"/api/v1/workspaces/{workspace['id']}")
    assert still_visible.status_code == 404


def test_sole_owner_cannot_leave(client: TestClient) -> None:
    owner_body = _register(client)
    workspace = _create_workspace(client)

    response = client.delete(
        f"/api/v1/workspaces/{workspace['id']}/members/{owner_body['user']['id']}",
        headers=csrf_headers(client),
    )

    assert response.status_code == 409


def test_admin_cannot_remove_another_admin(client_factory: Callable[[], TestClient]) -> None:
    owner = client_factory()
    admin_one = client_factory()
    admin_two = client_factory()
    _register(owner)
    admin_one_body = _register(admin_one)
    admin_two_body = _register(admin_two)
    workspace = _create_workspace(owner)
    _add_member(owner, workspace["id"], admin_one_body["user"]["email"], "ADMIN")
    _add_member(owner, workspace["id"], admin_two_body["user"]["email"], "ADMIN")

    response = admin_one.delete(
        f"/api/v1/workspaces/{workspace['id']}/members/{admin_two_body['user']['id']}",
        headers=csrf_headers(admin_one),
    )

    assert response.status_code == 403


# --- Cross-workspace isolation / IDOR (Issue #2's explicit security requirement) ---


def test_non_member_cannot_read_another_users_workspace(
    client_factory: Callable[[], TestClient],
) -> None:
    owner = client_factory()
    attacker = client_factory()
    _register(owner)
    _register(attacker)
    workspace = _create_workspace(owner)

    response = attacker.get(f"/api/v1/workspaces/{workspace['id']}")

    assert response.status_code == 404


def test_non_member_cannot_modify_another_users_workspace(
    client_factory: Callable[[], TestClient],
) -> None:
    owner = client_factory()
    attacker = client_factory()
    _register(owner)
    _register(attacker)
    workspace = _create_workspace(owner)

    response = attacker.patch(
        f"/api/v1/workspaces/{workspace['id']}",
        json={"name": "Pwned"},
        headers=csrf_headers(attacker),
    )

    assert response.status_code == 404
    assert owner.get(f"/api/v1/workspaces/{workspace['id']}").json()["name"] == "Acme"


def test_non_member_cannot_delete_another_users_workspace(
    client_factory: Callable[[], TestClient],
) -> None:
    owner = client_factory()
    attacker = client_factory()
    _register(owner)
    _register(attacker)
    workspace = _create_workspace(owner)

    response = attacker.delete(
        f"/api/v1/workspaces/{workspace['id']}", headers=csrf_headers(attacker)
    )

    assert response.status_code == 404
    assert owner.get(f"/api/v1/workspaces/{workspace['id']}").status_code == 200


def test_non_member_cannot_list_another_users_workspace_members(
    client_factory: Callable[[], TestClient],
) -> None:
    owner = client_factory()
    attacker = client_factory()
    _register(owner)
    _register(attacker)
    workspace = _create_workspace(owner)

    response = attacker.get(f"/api/v1/workspaces/{workspace['id']}/members")

    assert response.status_code == 404


def test_non_member_cannot_add_members_to_another_users_workspace(
    client_factory: Callable[[], TestClient],
) -> None:
    owner = client_factory()
    attacker = client_factory()
    _register(owner)
    _register(attacker)
    workspace = _create_workspace(owner)

    response = attacker.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": _unique_email(), "role": "MEMBER"},
        headers=csrf_headers(attacker),
    )

    assert response.status_code == 404


def test_nonexistent_workspace_id_returns_404_not_a_server_error(client: TestClient) -> None:
    _register(client)

    response = client.get(f"/api/v1/workspaces/{uuid.uuid4()}")

    assert response.status_code == 404


def test_malformed_workspace_id_is_rejected_as_invalid_input(client: TestClient) -> None:
    _register(client)

    response = client.get("/api/v1/workspaces/not-a-uuid")

    assert response.status_code == 422


def test_revoked_session_access_token_still_works_until_expiry_but_refresh_is_dead(
    client: TestClient,
) -> None:
    """Documents the ADR 0003 tradeoff this implementation makes: access
    tokens are validated without a DB round-trip, so revoking a session
    does not retroactively invalidate an already-issued, unexpired access
    token — only its refresh capability. This is bounded by the token's
    short expiry, not indefinite.

    Logout also clears the *current* client's access-token cookie (correct
    browser behavior), so this test captures the token's value beforehand
    and re-presents it afterward — simulating a copy of the cookie that
    outlived the logout response (e.g. a second tab, or a client that
    hadn't processed the `Set-Cookie` deletion yet), which is exactly the
    scenario the ADR 0003 tradeoff is about.
    """
    _register(client)
    headers = csrf_headers(client)
    workspace = _create_workspace(client)
    access_token_before_logout = client.cookies.get("access_token")

    client.post("/api/v1/auth/logout", headers=headers)
    client.cookies.set("access_token", access_token_before_logout)

    still_works = client.get(f"/api/v1/workspaces/{workspace['id']}")
    assert still_works.status_code == 200

    refresh_after_logout = client.post("/api/v1/auth/refresh", headers=headers)
    assert refresh_after_logout.status_code == 401
