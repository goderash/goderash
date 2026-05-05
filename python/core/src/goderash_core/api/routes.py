"""HTTP routes.

v1 surface:
- POST /v1/events         — ingest a batch of events (idempotent)
- GET  /v1/events         — query events for the authed tenant
- POST /v1/verify         — re-verify the hash chain for a window
- GET  /health            — liveness
- GET  /ready             — readiness (DB reachable)

Admin-only (require ADMIN_API_KEY):
- POST /v1/admin/tenants  — create a tenant
- POST /v1/admin/keys     — issue an API key for a tenant (returns raw key once)
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..billing.usage import get_usage, increment_usage, is_quota_exceeded, quota_warning_threshold
from ..config import get_settings
from ..db import session_scope
from ..events.types import GoderashEventEnvelope
from ..ledger.chain import verify_chain
from ..ledger.store import EventLedger
from ..models.event import EventRow
from ..models.tenant import ApiKey, Tenant
from ..webhooks.dispatcher import EVENT_CHAIN_BROKEN, EVENT_QUOTA_WARNING, dispatch
from .auth import AuthContext, _hash_key, require_admin, require_api_key

router = APIRouter()


# ---- Dependencies -----------------------------------------------------------


async def _redis() -> aioredis.Redis | None:
    settings = get_settings()
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.ping()
        return r
    except Exception:
        return None


# ---- Schemas ----------------------------------------------------------------


class IngestRequest(BaseModel):
    events: list[GoderashEventEnvelope] = Field(..., min_length=1, max_length=500)


class IngestResponse(BaseModel):
    accepted: int
    first_event_id: str
    last_event_id: str


class EventOut(BaseModel):
    event_id: str
    sequence_no: int
    event_type: str
    conversation_id: str
    turn_id: str
    occurred_at: datetime
    payload: dict[str, Any]
    prev_hash: str
    hash: str


class VerifyRequest(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    limit: int | None = Field(default=None, ge=1, le=10_000)


class VerifyResponse(BaseModel):
    ok: bool
    checked: int
    first_broken_index: int | None = None


class CreateTenantRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9\-_]*$")
    display_name: str = Field(..., min_length=1, max_length=255)


class CreateApiKeyRequest(BaseModel):
    tenant_id: str
    label: str = Field(..., min_length=1, max_length=128)


class CreateApiKeyResponse(BaseModel):
    api_key: str  # only ever returned here
    id: str
    tenant_id: str
    label: str


# ---- Liveness --------------------------------------------------------------


@router.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", tags=["meta"])
async def ready() -> dict[str, str]:
    async with session_scope() as session:
        await session.execute(text("SELECT 1"))
    return {"status": "ready"}


# ---- Events ----------------------------------------------------------------


async def _session() -> AsyncSession:
    async with session_scope() as s:
        yield s


async def _check_ingest_rate(
    redis: aioredis.Redis | None,
    tenant_id: str,
    batch_size: int,
    limit_per_minute: int,
) -> None:
    """Sliding per-tenant rate limit using a Redis counter keyed by minute."""
    if redis is None:
        return  # Redis unavailable — degrade gracefully
    from datetime import datetime, timezone

    minute_key = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M")
    key = f"gdr:rate:ingest:{tenant_id}:{minute_key}"
    try:
        current = await redis.incrby(key, batch_size)
        if current == batch_size:
            await redis.expire(key, 90)  # 90s TTL: covers the full minute + buffer
        if current > limit_per_minute:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"ingest rate limit of {limit_per_minute:,} events/min exceeded for this tenant",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Redis blip — never fail ingestion


@router.post(
    "/v1/events",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["events"],
)
async def ingest_events(
    body: IngestRequest = Body(...),
    auth: AuthContext = Depends(require_api_key),
    session: AsyncSession = Depends(_session),
    redis: aioredis.Redis | None = Depends(_redis),
) -> IngestResponse:
    settings = get_settings()

    if len(body.events) > settings.max_event_batch_size:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "batch too large")

    # Per-tenant rate limit
    await _check_ingest_rate(redis, auth.tenant_id, len(body.events), settings.ingest_rate_limit_per_minute)

    # Tenant isolation: every envelope must match the authed tenant.
    for env in body.events:
        if env.tenant_id != auth.tenant_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"envelope tenant_id {env.tenant_id!r} != authed tenant {auth.tenant_id!r}",
            )

    # Quota enforcement: Hobby plan hard limit.
    tenant_row = (await session.execute(select(Tenant).where(Tenant.id == auth.tenant_id))).scalar_one_or_none()
    if tenant_row is not None:
        current_usage = await get_usage(auth.tenant_id, redis=redis, session=session)
        quota = tenant_row.monthly_event_quota

        if is_quota_exceeded(current_usage, quota):
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                f"Monthly event quota of {quota:,} reached. "
                "Upgrade your plan at goderash.com/pricing.",
            )

        # Fire quota.warning webhook at 80% — best-effort, don't block ingest.
        warn = quota_warning_threshold(quota)
        if warn > 0 and current_usage < warn <= current_usage + len(body.events):
            await dispatch(session, auth.tenant_id, EVENT_QUOTA_WARNING, {
                "quota": quota,
                "used": current_usage,
                "threshold_pct": 80,
            })

    ledger = EventLedger(session)
    stored = await ledger.append_many(auth.tenant_id, body.events)

    # Increment Redis usage counter (best-effort — never fail the request).
    if redis is not None:
        await increment_usage(redis, auth.tenant_id, len(stored))

    return IngestResponse(
        accepted=len(stored),
        first_event_id=str(stored[0].event_id),
        last_event_id=str(stored[-1].event_id),
    )


@router.get("/v1/events", tags=["events"])
async def list_events(
    conversation_id: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    auth: AuthContext = Depends(require_api_key),
    session: AsyncSession = Depends(_session),
) -> list[EventOut]:
    stmt = select(EventRow).where(EventRow.tenant_id == auth.tenant_id)
    if conversation_id is not None:
        stmt = stmt.where(EventRow.conversation_id == conversation_id)
    if start is not None:
        stmt = stmt.where(EventRow.occurred_at >= start)
    if end is not None:
        stmt = stmt.where(EventRow.occurred_at <= end)
    stmt = stmt.order_by(EventRow.sequence_no.asc()).limit(limit)

    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        EventOut(
            event_id=str(r.event_id),
            sequence_no=r.sequence_no,
            event_type=r.event_type,
            conversation_id=r.conversation_id,
            turn_id=r.turn_id,
            occurred_at=r.occurred_at,
            payload=r.payload,
            prev_hash=r.prev_hash,
            hash=r.hash,
        )
        for r in rows
    ]


@router.post("/v1/verify", tags=["events"])
async def verify(
    body: VerifyRequest,
    auth: AuthContext = Depends(require_api_key),
    session: AsyncSession = Depends(_session),
) -> VerifyResponse:
    ledger = EventLedger(session)
    rows = await ledger.iter_tenant(
        auth.tenant_id, start=body.start, end=body.end, limit=body.limit
    )
    ok, broken = verify_chain(
        [
            {"prev_hash": r.prev_hash, "hash": r.hash, "payload": r.payload}
            for r in rows
        ]
    )
    # Fire chain.broken webhook asynchronously — never block the verify response.
    if not ok:
        await dispatch(session, auth.tenant_id, EVENT_CHAIN_BROKEN, {
            "ok": False,
            "checked": len(rows),
            "first_broken_index": broken,
        })
    return VerifyResponse(ok=ok, checked=len(rows), first_broken_index=broken)


# ---- Admin -----------------------------------------------------------------


@router.post(
    "/v1/admin/tenants",
    status_code=status.HTTP_201_CREATED,
    tags=["admin"],
)
async def create_tenant(
    body: CreateTenantRequest,
    _: AuthContext = Depends(require_admin),
    session: AsyncSession = Depends(_session),
) -> dict[str, str]:
    tenant = Tenant(id=body.id, display_name=body.display_name)
    session.add(tenant)
    return {"id": body.id, "display_name": body.display_name}


@router.post(
    "/v1/admin/keys",
    status_code=status.HTTP_201_CREATED,
    tags=["admin"],
)
async def create_api_key(
    body: CreateApiKeyRequest,
    _: AuthContext = Depends(require_admin),
    session: AsyncSession = Depends(_session),
) -> CreateApiKeyResponse:
    # Ensure tenant exists.
    existing = await session.execute(select(Tenant).where(Tenant.id == body.tenant_id))
    if existing.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")

    raw = f"{get_settings().api_key_prefix}{secrets.token_urlsafe(32)}"
    key = ApiKey(tenant_id=body.tenant_id, label=body.label, key_hash=_hash_key(raw))
    session.add(key)
    await session.flush()

    return CreateApiKeyResponse(
        api_key=raw,
        id=str(key.id),
        tenant_id=body.tenant_id,
        label=body.label,
    )
