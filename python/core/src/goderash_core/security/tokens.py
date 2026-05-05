"""Session JWTs for the dashboard.

These are short-lived tokens used by the Next.js dashboard. SDKs continue to
authenticate with API keys (X-Goderash-Api-Key) — JWTs are dashboard-only.

Two token types:
- access:  ~30 min, used for every API call
- refresh: ~30 days, used to rotate access tokens

Both are signed with the same HS256 secret from settings. The `kind` claim
distinguishes them so a refresh token can never be passed off as an access
token.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

import jwt

from ..config import get_settings

ACCESS_TTL = timedelta(minutes=30)
REFRESH_TTL = timedelta(days=30)

TokenKind = Literal["access", "refresh"]


@dataclass(frozen=True)
class SessionClaims:
    """Decoded JWT claims for a logged-in dashboard user."""

    user_id: UUID
    email: str
    kind: TokenKind
    exp: datetime
    iat: datetime
    jti: str


def issue_session_token(
    *, user_id: UUID, email: str, kind: TokenKind, jti: str
) -> tuple[str, datetime]:
    """Sign a fresh JWT. Returns (token, expires_at)."""
    s = get_settings()
    now = datetime.now(tz=timezone.utc)
    ttl = ACCESS_TTL if kind == "access" else REFRESH_TTL
    exp = now + ttl
    payload = {
        "sub": str(user_id),
        "email": email,
        "kind": kind,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": jti,
        "iss": "goderash",
    }
    token = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    return token, exp


def decode_session_token(token: str, *, expected_kind: TokenKind) -> SessionClaims:
    """Decode + validate a JWT. Raises jwt.PyJWTError on any failure."""
    s = get_settings()
    payload = jwt.decode(
        token,
        s.jwt_secret,
        algorithms=[s.jwt_algorithm],
        issuer="goderash",
        options={"require": ["sub", "email", "kind", "exp", "iat", "jti"]},
    )
    if payload.get("kind") != expected_kind:
        raise jwt.InvalidTokenError(
            f"token kind mismatch: expected {expected_kind!r}, got {payload.get('kind')!r}"
        )
    return SessionClaims(
        user_id=UUID(payload["sub"]),
        email=payload["email"],
        kind=payload["kind"],
        exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
        jti=payload["jti"],
    )
