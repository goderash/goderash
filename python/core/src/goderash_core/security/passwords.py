"""Argon2id password hashing.

Argon2id is the OWASP-recommended default. Parameters tuned for ~250ms on
modern server hardware — the right side of the latency/security tradeoff for
interactive logins.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# OWASP recommended starter params for Argon2id (Apr 2024 baseline).
# t=3 iterations, m=64MiB, p=4 parallel lanes.
_HASHER = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)


def hash_password(plain: str) -> str:
    """Return an Argon2id hash. Raises ValueError on empty input."""
    if not plain:
        raise ValueError("password must not be empty")
    return _HASHER.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time-ish verify. Returns False on any mismatch (no leaks)."""
    if not plain or not hashed:
        return False
    try:
        return _HASHER.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        # Malformed hash, library error, etc — fail closed.
        return False
