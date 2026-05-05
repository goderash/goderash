"""Redis-backed event usage counter with DB fallback.

Key schema:
    goderash:usage:{tenant_id}:{YYYY-MM}  → integer (total events in period)

The counter is incremented on every successful ingest batch. It is best-effort:
if Redis is unavailable we fall back to a DB COUNT query. The DB is always the
authoritative source for billing disputes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.event import EventRow

log = logging.getLogger(__name__)

_COUNTER_TTL_SECONDS = 40 * 24 * 3600  # 40 days — outlasts any billing period


def _period_key(tenant_id: str, period: str) -> str:
    return f"goderash:usage:{tenant_id}:{period}"


def _current_period() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m")


async def increment_usage(redis: aioredis.Redis, tenant_id: str, count: int) -> None:
    """Increment the usage counter for the current billing period."""
    key = _period_key(tenant_id, _current_period())
    try:
        pipe = redis.pipeline()
        pipe.incrby(key, count)
        pipe.expire(key, _COUNTER_TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:
        log.warning("billing.usage.redis_increment_failed", tenant_id=tenant_id, error=str(exc))


async def get_usage_from_redis(redis: aioredis.Redis, tenant_id: str) -> int | None:
    """Return current-period event count from Redis, or None if unavailable."""
    key = _period_key(tenant_id, _current_period())
    try:
        val = await redis.get(key)
        return int(val) if val is not None else 0
    except Exception as exc:
        log.warning("billing.usage.redis_get_failed", tenant_id=tenant_id, error=str(exc))
        return None


async def get_usage_from_db(session: AsyncSession, tenant_id: str) -> int:
    """Count events for the current billing month directly from the ledger."""
    now = datetime.now(tz=timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(func.count())
        .select_from(EventRow)
        .where(
            EventRow.tenant_id == tenant_id,
            EventRow.occurred_at >= period_start,
        )
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def get_usage(
    tenant_id: str,
    *,
    redis: aioredis.Redis | None,
    session: AsyncSession,
) -> int:
    """Return current-period event count, preferring Redis, falling back to DB."""
    if redis is not None:
        count = await get_usage_from_redis(redis, tenant_id)
        if count is not None:
            return count
    return await get_usage_from_db(session, tenant_id)


def is_quota_exceeded(current_usage: int, quota: int) -> bool:
    """Return True when the hard quota is exhausted (quota=-1 means unlimited)."""
    return quota != -1 and current_usage >= quota


def quota_warning_threshold(quota: int) -> int:
    """80% of quota — used to fire quota.warning webhooks."""
    return int(quota * 0.8)
