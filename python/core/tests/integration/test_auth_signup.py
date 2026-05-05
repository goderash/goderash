"""End-to-end self-serve onboarding: signup → login → me → keys.

Requires Postgres (UUID columns + advisory locks). Skipped automatically if
GODERASH_TEST_DATABASE_URL doesn't point to a postgres DSN.
"""

from __future__ import annotations

import os
from typing import AsyncIterator
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    "postgresql" not in os.environ.get("GODERASH_TEST_DATABASE_URL", ""),
    reason="requires a real Postgres (set GODERASH_TEST_DATABASE_URL)",
)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    from goderash_core.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _new_email() -> str:
    return f"founder-{uuid4().hex[:10]}@example.com"


async def test_signup_returns_user_tenant_key_and_tokens(client: httpx.AsyncClient) -> None:
    email = _new_email()
    r = await client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "long-enough-password-1234",
            "full_name": "Test Founder",
            "org_name": "Acme AI",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()

    # Identity surface
    assert body["email"] == email
    assert body["tenant_id"]
    assert body["api_key"].startswith("gdr_")
    assert "user_id" in body

    # Tokens
    tokens = body["tokens"]
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"


async def test_duplicate_signup_rejected(client: httpx.AsyncClient) -> None:
    email = _new_email()
    payload = {
        "email": email,
        "password": "long-enough-password-1234",
        "full_name": "Dup Test",
    }
    r1 = await client.post("/v1/auth/signup", json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/v1/auth/signup", json=payload)
    assert r2.status_code == 409


async def test_login_then_me_returns_membership(client: httpx.AsyncClient) -> None:
    email = _new_email()
    signup = await client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "long-enough-password-1234",
            "full_name": "Me Tester",
        },
    )
    assert signup.status_code == 201

    login = await client.post(
        "/v1/auth/login",
        json={"email": email, "password": "long-enough-password-1234"},
    )
    assert login.status_code == 200, login.text
    access = login.json()["access_token"]

    me = await client.get(
        "/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["email"] == email
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["role"] == "owner"


async def test_login_with_wrong_password_returns_401(client: httpx.AsyncClient) -> None:
    email = _new_email()
    await client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "long-enough-password-1234",
            "full_name": "Bad Pass",
        },
    )
    r = await client.post(
        "/v1/auth/login",
        json={"email": email, "password": "wrong-password-but-long-enough"},
    )
    assert r.status_code == 401


async def test_login_for_unknown_email_returns_401(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/v1/auth/login",
        json={"email": "ghost@example.com", "password": "any-long-password"},
    )
    assert r.status_code == 401


async def test_refresh_returns_new_pair(client: httpx.AsyncClient) -> None:
    email = _new_email()
    s = await client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "long-enough-password-1234",
            "full_name": "Refresh User",
        },
    )
    refresh_token = s.json()["tokens"]["refresh_token"]

    r = await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    new_tokens = r.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]


async def test_me_without_token_returns_401(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/auth/me")
    assert r.status_code == 401


async def test_keys_lifecycle_for_authenticated_user(client: httpx.AsyncClient) -> None:
    """Owner can list, issue, and revoke keys on their own tenant."""
    email = _new_email()
    s = await client.post(
        "/v1/auth/signup",
        json={
            "email": email,
            "password": "long-enough-password-1234",
            "full_name": "Keys User",
        },
    )
    assert s.status_code == 201
    tenant_id = s.json()["tenant_id"]
    access = s.json()["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    # List → exactly the bootstrap "default" key.
    r = await client.get(f"/v1/orgs/{tenant_id}/keys", headers=headers)
    assert r.status_code == 200
    keys = r.json()
    assert len(keys) == 1
    assert keys[0]["label"] == "default"

    # Issue a second key.
    r = await client.post(
        f"/v1/orgs/{tenant_id}/keys",
        headers=headers,
        json={"label": "ci"},
    )
    assert r.status_code == 201
    new_key = r.json()
    assert new_key["api_key"].startswith("gdr_")
    new_key_id = new_key["id"]

    # Now there are two.
    r = await client.get(f"/v1/orgs/{tenant_id}/keys", headers=headers)
    assert len(r.json()) == 2

    # Revoke the new one.
    r = await client.delete(f"/v1/orgs/{tenant_id}/keys/{new_key_id}", headers=headers)
    assert r.status_code == 204

    # It's still listed but revoked_at is set.
    r = await client.get(f"/v1/orgs/{tenant_id}/keys", headers=headers)
    revoked = next(k for k in r.json() if k["id"] == new_key_id)
    assert revoked["revoked_at"] is not None


async def test_user_cannot_touch_someone_elses_tenant(client: httpx.AsyncClient) -> None:
    """Hitting another tenant's keys endpoint must 404 (no existence leak)."""
    a_email = _new_email()
    b_email = _new_email()

    a = await client.post(
        "/v1/auth/signup",
        json={
            "email": a_email,
            "password": "long-enough-password-1234",
            "full_name": "User A",
        },
    )
    b = await client.post(
        "/v1/auth/signup",
        json={
            "email": b_email,
            "password": "long-enough-password-1234",
            "full_name": "User B",
        },
    )
    a_tenant = a.json()["tenant_id"]
    b_access = b.json()["tokens"]["access_token"]

    r = await client.get(
        f"/v1/orgs/{a_tenant}/keys",
        headers={"Authorization": f"Bearer {b_access}"},
    )
    assert r.status_code == 404
