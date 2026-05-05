"""Session JWT issuance + verification — unit tests."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from goderash_core.security.tokens import (
    ACCESS_TTL,
    REFRESH_TTL,
    decode_session_token,
    issue_session_token,
)


def test_access_token_roundtrip() -> None:
    uid = uuid4()
    token, exp = issue_session_token(
        user_id=uid, email="founder@example.com", kind="access", jti="jti-abc"
    )
    claims = decode_session_token(token, expected_kind="access")
    assert claims.user_id == uid
    assert claims.email == "founder@example.com"
    assert claims.kind == "access"
    assert claims.jti == "jti-abc"
    # Expiry is roughly ACCESS_TTL away from now; allow 5s of slack.
    expected = datetime.now(tz=timezone.utc) + ACCESS_TTL
    assert abs((exp - expected).total_seconds()) < 5


def test_refresh_token_lives_longer_than_access() -> None:
    _, access_exp = issue_session_token(
        user_id=uuid4(), email="a@b.com", kind="access", jti="j1"
    )
    _, refresh_exp = issue_session_token(
        user_id=uuid4(), email="a@b.com", kind="refresh", jti="j2"
    )
    assert refresh_exp - access_exp > timedelta(days=1)
    assert refresh_exp - access_exp < REFRESH_TTL + timedelta(minutes=1)


def test_kind_mismatch_is_rejected() -> None:
    """An access token must not be usable where a refresh token is expected."""
    token, _ = issue_session_token(
        user_id=uuid4(), email="x@y.com", kind="access", jti="j"
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_session_token(token, expected_kind="refresh")


def test_tampered_signature_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    token, _ = issue_session_token(
        user_id=uuid4(), email="x@y.com", kind="access", jti="j"
    )
    # Flip the last byte of the signature → must fail.
    bad = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_session_token(bad, expected_kind="access")


def test_expired_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """If exp is in the past, decode raises ExpiredSignatureError."""
    from goderash_core.security import tokens as tokens_module

    monkeypatch.setattr(tokens_module, "ACCESS_TTL", timedelta(seconds=-1))
    token, _ = issue_session_token(
        user_id=uuid4(), email="x@y.com", kind="access", jti="j"
    )
    # Tiny pause to ensure clock has moved past the issued exp.
    time.sleep(0.05)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_session_token(token, expected_kind="access")


def test_missing_required_claim_rejected() -> None:
    """A token forged without the required claims is rejected."""
    from goderash_core.config import get_settings

    s = get_settings()
    forged = jwt.encode(
        {"hello": "world", "iss": "goderash"}, s.jwt_secret, algorithm=s.jwt_algorithm
    )
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_session_token(forged, expected_kind="access")
