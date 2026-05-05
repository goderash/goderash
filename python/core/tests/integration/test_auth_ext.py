"""Integration tests: password reset, email verification, token revocation, change-password.

Requires Postgres. Skipped automatically unless GODERASH_TEST_DATABASE_URL is set.
"""

from __future__ import annotations

import hashlib
import os
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
    return f"test-{uuid4().hex[:8]}@example.com"


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


# ── Forgot / Reset password ──────────────────────────────────────────────────

async def test_forgot_password_always_202(client: httpx.AsyncClient) -> None:
    # Unknown email must also return 202 — no user enumeration.
    r = await client.post("/v1/auth/forgot-password", json={"email": "ghost@example.com"})
    assert r.status_code == 202


async def test_forgot_password_known_email_creates_token(client: httpx.AsyncClient) -> None:
    from sqlalchemy import select
    from goderash_core.db import session_scope
    from goderash_core.models.auth_tokens import PasswordResetToken
    from goderash_core.models.user import User

    email = _email()
    await _signup(client, email)

    r = await client.post("/v1/auth/forgot-password", json={"email": email})
    assert r.status_code == 202

    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one()
        tokens = (
            await s.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
        ).scalars().all()
    assert len(tokens) == 1
    assert tokens[0].expires_at > datetime.now(tz=timezone.utc)


async def test_reset_password_with_valid_token(client: httpx.AsyncClient) -> None:
    from sqlalchemy import select
    from goderash_core.db import session_scope
    from goderash_core.models.auth_tokens import PasswordResetToken
    from goderash_core.models.user import User
    from goderash_core.api.auth_public import _hash_token

    email = _email()
    await _signup(client, email)

    # Create a reset token directly in the DB (avoids needing real email)
    raw_token = "test-reset-token-thats-long-enough-to-be-valid-xyz"
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one()
        prt = PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )
        s.add(prt)

    r = await client.post(
        "/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-password-5678"},
    )
    assert r.status_code == 200, r.text

    # Old password no longer works
    bad = await client.post(
        "/v1/auth/login", json={"email": email, "password": "long-enough-password-1234"}
    )
    assert bad.status_code == 401

    # New password works
    ok = await client.post(
        "/v1/auth/login", json={"email": email, "password": "brand-new-password-5678"}
    )
    assert ok.status_code == 200


async def test_reset_password_token_cannot_be_reused(client: httpx.AsyncClient) -> None:
    from sqlalchemy import select
    from goderash_core.db import session_scope
    from goderash_core.models.auth_tokens import PasswordResetToken
    from goderash_core.models.user import User
    from goderash_core.api.auth_public import _hash_token

    email = _email()
    await _signup(client, email)

    raw_token = "one-time-reset-token-that-should-only-work-once-123"
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one()
        s.add(PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        ))

    await client.post(
        "/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "brand-new-password-5678"},
    )
    # Second use must fail
    r = await client.post(
        "/v1/auth/reset-password",
        json={"token": raw_token, "new_password": "another-password-1234"},
    )
    assert r.status_code == 400


async def test_reset_password_invalid_token_returns_400(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/v1/auth/reset-password",
        json={"token": "totally-bogus-token-that-does-not-exist-xyz", "new_password": "anything-long-enough"},
    )
    assert r.status_code == 400


# ── Email verification ────────────────────────────────────────────────────────

async def test_verify_email_with_valid_token(client: httpx.AsyncClient) -> None:
    from sqlalchemy import select
    from goderash_core.db import session_scope
    from goderash_core.models.auth_tokens import EmailVerificationToken
    from goderash_core.models.user import User
    from goderash_core.api.auth_public import _hash_token

    email = _email()
    await _signup(client, email)

    raw = "valid-email-verification-token-long-enough-12345"
    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one()
        s.add(EmailVerificationToken(
            user_id=user.id,
            token_hash=_hash_token(raw),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=24),
        ))

    r = await client.get(f"/v1/auth/verify-email?token={raw}")
    assert r.status_code == 200

    async with session_scope() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one()
    assert user.email_verified_at is not None


async def test_verify_email_invalid_token_returns_400(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/auth/verify-email?token=bogus-token-that-definitely-does-not-exist")
    assert r.status_code == 400


# ── Token revocation (logout) ────────────────────────────────────────────────

async def test_logout_revokes_access_token(client: httpx.AsyncClient) -> None:
    data = await _signup(client)
    access = data["tokens"]["access_token"]
    refresh = data["tokens"]["refresh_token"]
    headers = {"Authorization": f"Bearer {access}"}

    # /me works before logout
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 200

    # Logout
    r = await client.post(
        "/v1/auth/logout",
        json={"refresh_token": refresh},
        headers=headers,
    )
    assert r.status_code == 204

    # /me must now fail (access token revoked)
    assert (await client.get("/v1/auth/me", headers=headers)).status_code == 401


# ── Change password ──────────────────────────────────────────────────────────

async def test_change_password_success(client: httpx.AsyncClient) -> None:
    email = _email()
    data = await _signup(client, email)
    access = data["tokens"]["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    r = await client.post(
        "/v1/auth/change-password",
        json={
            "current_password": "long-enough-password-1234",
            "new_password": "brand-spanking-new-password-5678",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    ok = await client.post(
        "/v1/auth/login",
        json={"email": email, "password": "brand-spanking-new-password-5678"},
    )
    assert ok.status_code == 200


async def test_change_password_wrong_current_returns_400(client: httpx.AsyncClient) -> None:
    data = await _signup(client)
    headers = {"Authorization": f"Bearer {data['tokens']['access_token']}"}

    r = await client.post(
        "/v1/auth/change-password",
        json={"current_password": "wrong-password-long-enough", "new_password": "new-pw-123456789"},
        headers=headers,
    )
    assert r.status_code == 400
