from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

_PASSWORD = "correct horse battery staple"


def _unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def _register(
    client: TestClient, email: str | None = None
) -> tuple[dict[str, Any], dict[str, str]]:
    email = email or _unique_email()
    response = client.post(
        "/api/v1/auth/register", json={"email": email, "password": _PASSWORD}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


def _create_workspace(
    client: TestClient, headers: dict[str, str], name: str = "Acme"
) -> dict[str, Any]:
    response = client.post("/api/v1/workspaces", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def test_create_workspace_makes_creator_owner(client: TestClient) -> None:
    _, headers = _register(client)

    workspace = _create_workspace(client, headers)

    assert workspace["name"] == "Acme"
    assert workspace["my_role"] == "OWNER"


def test_list_workspaces_returns_only_memberships(client: TestClient) -> None:
    _, headers_a = _register(client)
    _, headers_b = _register(client)
    _create_workspace(client, headers_a, "A's workspace")
    _create_workspace(client, headers_b, "B's workspace")

    response = client.get("/api/v1/workspaces", headers=headers_a)

    assert response.status_code == 200
    names = {w["name"] for w in response.json()}
    assert names == {"A's workspace"}


def test_get_workspace_requires_authentication(client: TestClient) -> None:
    _, headers = _register(client)
    workspace = _create_workspace(client, headers)

    response = client.get(f"/api/v1/workspaces/{workspace['id']}")

    assert response.status_code == 401


def test_update_workspace_name_by_owner(client: TestClient) -> None:
    _, headers = _register(client)
    workspace = _create_workspace(client, headers)

    response = client.patch(
        f"/api/v1/workspaces/{workspace['id']}", json={"name": "New Name"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


def test_delete_workspace_by_owner(client: TestClient) -> None:
    _, headers = _register(client)
    workspace = _create_workspace(client, headers)

    response = client.delete(f"/api/v1/workspaces/{workspace['id']}", headers=headers)

    assert response.status_code == 204
    assert client.get(f"/api/v1/workspaces/{workspace['id']}", headers=headers).status_code == 404


def _add_member(
    client: TestClient, headers: dict[str, str], workspace_id: str, email: str, role: str
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": email, "role": role},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def test_owner_can_add_member(client: TestClient) -> None:
    _, owner_headers = _register(client)
    member_body, _ = _register(client)
    workspace = _create_workspace(client, owner_headers)

    added = _add_member(
        client, owner_headers, workspace["id"], member_body["user"]["email"], "MEMBER"
    )

    assert added["role"] == "MEMBER"
    assert added["email"] == member_body["user"]["email"]


def test_plain_member_cannot_add_members(client: TestClient) -> None:
    _, owner_headers = _register(client)
    member_body, member_headers = _register(client)
    workspace = _create_workspace(client, owner_headers)
    _add_member(client, owner_headers, workspace["id"], member_body["user"]["email"], "MEMBER")

    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": _unique_email(), "role": "MEMBER"},
        headers=member_headers,
    )

    assert response.status_code == 403


def test_admin_cannot_assign_owner_role(client: TestClient) -> None:
    _, owner_headers = _register(client)
    admin_body, admin_headers = _register(client)
    workspace = _create_workspace(client, owner_headers)
    _add_member(client, owner_headers, workspace["id"], admin_body["user"]["email"], "ADMIN")

    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": _unique_email(), "role": "OWNER"},
        headers=admin_headers,
    )

    assert response.status_code == 403


def test_admin_can_assign_member_and_viewer_roles(client: TestClient) -> None:
    _, owner_headers = _register(client)
    admin_body, admin_headers = _register(client)
    viewer_body, _ = _register(client)
    workspace = _create_workspace(client, owner_headers)
    _add_member(client, owner_headers, workspace["id"], admin_body["user"]["email"], "ADMIN")

    added = _add_member(
        client, admin_headers, workspace["id"], viewer_body["user"]["email"], "VIEWER"
    )

    assert added["role"] == "VIEWER"


def test_owner_can_promote_member_to_admin(client: TestClient) -> None:
    _, owner_headers = _register(client)
    member_body, _ = _register(client)
    workspace = _create_workspace(client, owner_headers)
    _add_member(client, owner_headers, workspace["id"], member_body["user"]["email"], "MEMBER")

    response = client.patch(
        f"/api/v1/workspaces/{workspace['id']}/members/{member_body['user']['id']}",
        json={"role": "ADMIN"},
        headers=owner_headers,
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"


def test_admin_cannot_change_another_admins_role(client: TestClient) -> None:
    _, owner_headers = _register(client)
    admin_one_body, admin_one_headers = _register(client)
    admin_two_body, _ = _register(client)
    workspace = _create_workspace(client, owner_headers)
    _add_member(client, owner_headers, workspace["id"], admin_one_body["user"]["email"], "ADMIN")
    _add_member(client, owner_headers, workspace["id"], admin_two_body["user"]["email"], "ADMIN")

    response = client.patch(
        f"/api/v1/workspaces/{workspace['id']}/members/{admin_two_body['user']['id']}",
        json={"role": "VIEWER"},
        headers=admin_one_headers,
    )

    assert response.status_code == 403


def test_cannot_demote_the_last_owner(client: TestClient) -> None:
    owner_body, owner_headers = _register(client)
    workspace = _create_workspace(client, owner_headers)

    response = client.patch(
        f"/api/v1/workspaces/{workspace['id']}/members/{owner_body['user']['id']}",
        json={"role": "ADMIN"},
        headers=owner_headers,
    )

    assert response.status_code == 409


def test_member_can_leave_workspace(client: TestClient) -> None:
    _, owner_headers = _register(client)
    member_body, member_headers = _register(client)
    workspace = _create_workspace(client, owner_headers)
    _add_member(client, owner_headers, workspace["id"], member_body["user"]["email"], "MEMBER")

    response = client.delete(
        f"/api/v1/workspaces/{workspace['id']}/members/{member_body['user']['id']}",
        headers=member_headers,
    )

    assert response.status_code == 204
    still_visible = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=member_headers)
    assert still_visible.status_code == 404


def test_sole_owner_cannot_leave(client: TestClient) -> None:
    owner_body, owner_headers = _register(client)
    workspace = _create_workspace(client, owner_headers)

    response = client.delete(
        f"/api/v1/workspaces/{workspace['id']}/members/{owner_body['user']['id']}",
        headers=owner_headers,
    )

    assert response.status_code == 409


def test_admin_cannot_remove_another_admin(client: TestClient) -> None:
    _, owner_headers = _register(client)
    admin_one_body, admin_one_headers = _register(client)
    admin_two_body, _ = _register(client)
    workspace = _create_workspace(client, owner_headers)
    _add_member(client, owner_headers, workspace["id"], admin_one_body["user"]["email"], "ADMIN")
    _add_member(client, owner_headers, workspace["id"], admin_two_body["user"]["email"], "ADMIN")

    response = client.delete(
        f"/api/v1/workspaces/{workspace['id']}/members/{admin_two_body['user']['id']}",
        headers=admin_one_headers,
    )

    assert response.status_code == 403


# --- Cross-workspace isolation / IDOR (Issue #2's explicit security requirement) ---


def test_non_member_cannot_read_another_users_workspace(client: TestClient) -> None:
    _, owner_headers = _register(client)
    _, attacker_headers = _register(client)
    workspace = _create_workspace(client, owner_headers)

    response = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=attacker_headers)

    assert response.status_code == 404


def test_non_member_cannot_modify_another_users_workspace(client: TestClient) -> None:
    _, owner_headers = _register(client)
    _, attacker_headers = _register(client)
    workspace = _create_workspace(client, owner_headers)

    response = client.patch(
        f"/api/v1/workspaces/{workspace['id']}",
        json={"name": "Pwned"},
        headers=attacker_headers,
    )

    assert response.status_code == 404
    # And the original workspace is genuinely untouched.
    assert client.get(f"/api/v1/workspaces/{workspace['id']}", headers=owner_headers).json()[
        "name"
    ] == "Acme"


def test_non_member_cannot_delete_another_users_workspace(client: TestClient) -> None:
    _, owner_headers = _register(client)
    _, attacker_headers = _register(client)
    workspace = _create_workspace(client, owner_headers)

    response = client.delete(f"/api/v1/workspaces/{workspace['id']}", headers=attacker_headers)

    assert response.status_code == 404
    still_there = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=owner_headers)
    assert still_there.status_code == 200


def test_non_member_cannot_list_another_users_workspace_members(client: TestClient) -> None:
    _, owner_headers = _register(client)
    _, attacker_headers = _register(client)
    workspace = _create_workspace(client, owner_headers)

    response = client.get(f"/api/v1/workspaces/{workspace['id']}/members", headers=attacker_headers)

    assert response.status_code == 404


def test_non_member_cannot_add_members_to_another_users_workspace(client: TestClient) -> None:
    _, owner_headers = _register(client)
    _, attacker_headers = _register(client)
    workspace = _create_workspace(client, owner_headers)

    response = client.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": _unique_email(), "role": "MEMBER"},
        headers=attacker_headers,
    )

    assert response.status_code == 404


def test_nonexistent_workspace_id_returns_404_not_a_server_error(client: TestClient) -> None:
    _, headers = _register(client)

    response = client.get(f"/api/v1/workspaces/{uuid.uuid4()}", headers=headers)

    assert response.status_code == 404


def test_malformed_workspace_id_is_rejected_as_invalid_input(client: TestClient) -> None:
    _, headers = _register(client)

    response = client.get("/api/v1/workspaces/not-a-uuid", headers=headers)

    assert response.status_code == 422


def test_revoked_session_access_token_still_works_until_expiry_but_refresh_is_dead(
    client: TestClient,
) -> None:
    """Documents the ADR 0003 tradeoff this implementation makes: access
    tokens are validated without a DB round-trip, so revoking a session
    does not retroactively invalidate an already-issued, unexpired access
    token — only its refresh capability. This is bounded by the token's
    short expiry, not indefinite."""
    tokens, headers = _register(client)
    workspace = _create_workspace(client, headers)

    client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    still_works = client.get(f"/api/v1/workspaces/{workspace['id']}", headers=headers)
    assert still_works.status_code == 200

    refresh_after_logout = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_after_logout.status_code == 401
