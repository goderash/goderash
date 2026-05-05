"""Integration tests: team invite flow — create, list, cancel, accept, remove member.

Requires Postgres. Skipped automatically unless GODERASH_TEST_DATABASE_URL is set.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
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


def _email() -> str:
    return f"invite-test-{uuid4().hex[:8]}@example.com"


async def _signup(client: httpx.AsyncClient, email: str | None = None) -> dict:
    r = await client.post(
        "/v1/auth/signup",
        json={
            "email": email or _email(),
            "password": "long-enough-password-1234",
            "full_name": "Test User",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _headers(data: dict) -> dict:
    return {"Authorization": f"Bearer {data['tokens']['access_token']}"}


# ── Create invite ─────────────────────────────────────────────────────────────

async def test_owner_can_create_invite(client: httpx.AsyncClient) -> None:
    owner = await _signup(client)
    tenant_id = owner["tenant_id"]
    h = await _headers(owner)

    r = await client.post(
        f"/v1/orgs/{tenant_id}/invites",
        headers=h,
        json={"email": _email(), "role": "developer"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"]
    assert body["role"] == "developer"


async def test_duplicate_pending_invite_rejected(client: httpx.AsyncClient) -> None:
    owner = await _signup(client)
    tenant_id = owner["tenant_id"]
    h = await _headers(owner)
    email = _email()

    r1 = await client.post(
        f"/v1/orgs/{tenant_id}/invites", headers=h, json={"email": email, "role": "developer"}
    )
    assert r1.status_code == 201

    r2 = await client.post(
        f"/v1/orgs/{tenant_id}/invites", headers=h, json={"email": email, "role": "developer"}
    )
    assert r2.status_code == 409


async def test_cannot_invite_existing_member(client: httpx.AsyncClient) -> None:
    owner = await _signup(client)
    tenant_id = owner["tenant_id"]
    h = await _headers(owner)

    # Try to invite yourself
    r = await client.post(
        f"/v1/orgs/{tenant_id}/invites",
        headers=h,
        json={"email": owner["email"], "role": "developer"},
    )
    assert r.status_code == 409


# ── List invites ──────────────────────────────────────────────────────────────

async def test_list_invites_returns_pending_only(client: httpx.AsyncClient) -> None:
    owner = await _signup(client)
    tenant_id = owner["tenant_id"]
    h = await _headers(owner)

    await client.post(
        f"/v1/orgs/{tenant_id}/invites", headers=h, json={"email": _email(), "role": "viewer"}
    )

    r = await client.get(f"/v1/orgs/{tenant_id}/invites", headers=h)
    assert r.status_code == 200
    assert len(r.json()) >= 1


# ── Cancel invite ─────────────────────────────────────────────────────────────

async def test_cancel_invite(client: httpx.AsyncClient) -> None:
    owner = await _signup(client)
    tenant_id = owner["tenant_id"]
    h = await _headers(owner)

    invite_r = await client.post(
        f"/v1/orgs/{tenant_id}/invites", headers=h, json={"email": _email(), "role": "viewer"}
    )
    invite_id = invite_r.json()["id"]

    r = await client.delete(f"/v1/orgs/{tenant_id}/invites/{invite_id}", headers=h)
    assert r.status_code == 204

    # Invite no longer appears in list
    list_r = await client.get(f"/v1/orgs/{tenant_id}/invites", headers=h)
    ids = [i["id"] for i in list_r.json()]
    assert invite_id not in ids


# ── Accept invite ─────────────────────────────────────────────────────────────

async def test_accept_invite_new_user(client: httpx.AsyncClient) -> None:
    from goderash_core.db import session_scope
    from goderash_core.models.auth_tokens import Invite
    from goderash_core.models.user import User
    from sqlalchemy import select

    owner = await _signup(client)
    tenant_id = owner["tenant_id"]
    h = await _headers(owner)
    invitee_email = _email()

    await client.post(
        f"/v1/orgs/{tenant_id}/invites",
        headers=h,
        json={"email": invitee_email, "role": "developer"},
    )

    # Grab the raw token from the DB (in real life it arrives by email)
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == invitee_email))).scalar_one_or_none()
        # Override the hashed token so we know the raw value
        inv = (
            await s.execute(
                select(Invite).where(
                    Invite.tenant_id == tenant_id, Invite.email == invitee_email
                )
            )
        ).scalar_one()
        inv.token_hash = token_hash

    r = await client.post(
        "/v1/auth/accept-invite",
        json={
            "token": raw_token,
            "full_name": "New Member",
            "password": "brand-new-member-password-xyz",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]

    # New member can now log in and see the workspace
    login_r = await client.post(
        "/v1/auth/login",
        json={"email": invitee_email, "password": "brand-new-member-password-xyz"},
    )
    assert login_r.status_code == 200
    access = login_r.json()["access_token"]
    me_r = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    tenant_ids = [m["tenant_id"] for m in me_r.json()["memberships"]]
    assert tenant_id in tenant_ids


async def test_accept_invite_expired_returns_400(client: httpx.AsyncClient) -> None:
    from goderash_core.db import session_scope
    from goderash_core.models.auth_tokens import Invite
    from sqlalchemy import select

    owner = await _signup(client)
    tenant_id = owner["tenant_id"]
    h = await _headers(owner)
    invitee_email = _email()

    await client.post(
        f"/v1/orgs/{tenant_id}/invites",
        headers=h,
        json={"email": invitee_email, "role": "developer"},
    )

    # Expire the invite
    async with session_scope() as s:
        inv = (
            await s.execute(
                select(Invite).where(
                    Invite.tenant_id == tenant_id, Invite.email == invitee_email
                )
            )
        ).scalar_one()
        inv.expires_at = datetime.now(tz=timezone.utc) - timedelta(seconds=1)

    r = await client.post(
        "/v1/auth/accept-invite",
        json={"token": "any-token-it-should-not-matter", "full_name": "X", "password": "pw-12345678"},
    )
    assert r.status_code == 400


# ── Member management ─────────────────────────────────────────────────────────

async def test_list_members_returns_owner(client: httpx.AsyncClient) -> None:
    owner = await _signup(client)
    tenant_id = owner["tenant_id"]
    h = await _headers(owner)

    r = await client.get(f"/v1/orgs/{tenant_id}/members", headers=h)
    assert r.status_code == 200
    members = r.json()
    assert len(members) == 1
    assert members[0]["role"] == "owner"
    assert members[0]["email"] == owner["email"]


async def test_cannot_remove_self(client: httpx.AsyncClient) -> None:
    owner = await _signup(client)
    tenant_id = owner["tenant_id"]
    h = await _headers(owner)

    r = await client.delete(
        f"/v1/orgs/{tenant_id}/members/{owner['user_id']}", headers=h
    )
    assert r.status_code == 400


async def test_nonmember_cannot_list_invites(client: httpx.AsyncClient) -> None:
    a = await _signup(client)
    b = await _signup(client)
    a_tenant = a["tenant_id"]
    b_headers = {"Authorization": f"Bearer {b['tokens']['access_token']}"}

    r = await client.get(f"/v1/orgs/{a_tenant}/invites", headers=b_headers)
    # Must 404 (not 403) to avoid leaking tenant existence
    assert r.status_code == 404
