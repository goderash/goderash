"""Argon2id password hashing — unit tests."""

from __future__ import annotations

import pytest

from goderash_core.security.passwords import hash_password, verify_password


def test_hash_then_verify_roundtrip() -> None:
    h = hash_password("correct-horse-battery-staple")
    assert h.startswith("$argon2")
    assert verify_password("correct-horse-battery-staple", h) is True


def test_verify_rejects_wrong_password() -> None:
    h = hash_password("super-secret-12345")
    assert verify_password("super-secret-1234X", h) is False


def test_verify_rejects_empty_input() -> None:
    h = hash_password("anything-long-enough")
    assert verify_password("", h) is False
    assert verify_password("anything-long-enough", "") is False


def test_verify_rejects_malformed_hash_without_raising() -> None:
    # A library error must surface as False, never an exception — fail closed.
    assert verify_password("any-password", "not-an-argon2-hash") is False


def test_hash_rejects_empty_password() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_each_hash_has_unique_salt() -> None:
    a = hash_password("identical-password-here")
    b = hash_password("identical-password-here")
    assert a != b
    assert verify_password("identical-password-here", a) is True
    assert verify_password("identical-password-here", b) is True
