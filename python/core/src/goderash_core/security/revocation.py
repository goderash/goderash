"""JTI revocation via Redis.

Access and refresh token JTIs are blocklisted on logout with a TTL equal to
the token's remaining lifetime. If Redis is unavailable, revocation is skipped
and we degrade gracefully (tokens remain valid until natural expiry).
"""

from __future__ import annotations

_PREFIX = "gdr:jti:blocked:"


async def revoke_jti(redis, jti: str, ttl_seconds: int) -> None:
    """Block a JTI until its natural expiry. No-ops if Redis is unavailable."""
    if redis is None or ttl_seconds <= 0:
        return
    try:
        await redis.setex(f"{_PREFIX}{jti}", ttl_seconds, "1")
    except Exception:
        pass  # Redis blip — degrade gracefully, log at call site if needed


async def is_jti_revoked(redis, jti: str) -> bool:
    """Return True if the JTI has been explicitly revoked. False on Redis failure."""
    if redis is None:
        return False
    try:
        return bool(await redis.exists(f"{_PREFIX}{jti}"))
    except Exception:
        return False
