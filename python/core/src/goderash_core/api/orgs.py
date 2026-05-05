"""Self-service org + API-key management for dashboard users.

Authenticated by JWT session (Authorization: Bearer ...). The acting user
must have an active membership on the targeted tenant — this is the
authorization boundary that keeps tenants isolated.

Endpoints:
- GET    /v1/orgs/{tenant_id}/usage             — current-period event usage
- GET    /v1/orgs/{tenant_id}/events            — event ledger (newest-first)
- GET    /v1/orgs/{tenant_id}/keys              — list keys (no secrets)
- POST   /v1/orgs/{tenant_id}/keys              — issue a new key (raw value once)
- DELETE /v1/orgs/{tenant_id}/keys/{key_id}     — revoke a key
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..billing.usage import get_usage, quota_warning_threshold
from ..config import get_settings
from ..db import session_scope
from ..ledger.store import EventLedger
from ..models.event import EventRow
from ..models.tenant import ApiKey, Tenant
from ..models.user import Membership, User
from ..packs import PACK_REGISTRY
from ..security import SessionClaims
from ..whatif import WhatIfPolicy, WhatIfProjector
from .auth import _hash_key
from .auth_public import require_session

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None  # type: ignore[assignment]

router = APIRouter(prefix="/v1/orgs", tags=["orgs"])


async def _session() -> AsyncSession:
    async with session_scope() as s:
        yield s


# ---- Schemas ----------------------------------------------------------------


class UsageOut(BaseModel):
    tenant_id: str
    plan: str
    period: str
    events_used: int
    quota: int
    quota_pct: float | None
    overage: int
    warning_threshold: int | None


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


class IssueKeyRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=128)


class IssueKeyResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str
    label: str
    api_key: str  # raw — returned exactly once
    created_at: datetime


class KeyOut(BaseModel):
    id: uuid.UUID
    tenant_id: str
    label: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class PackRequest(BaseModel):
    start: datetime | None = None
    end: datetime | None = None


class WhatIfPolicyIn(BaseModel):
    velocity_caps: dict[str, int] = Field(default_factory=dict)
    velocity_amount_caps: dict[str, float] = Field(default_factory=dict)
    deny_tools: list[str] = Field(default_factory=list)
    require_confirmation: list[str] = Field(default_factory=list)
    new_permission_mode: str | None = None


class WhatIfRequest(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    policy: WhatIfPolicyIn = Field(default_factory=WhatIfPolicyIn)


class CounterEvent(BaseModel):
    sequence_no: int
    event_type: str
    tool_name: str | None
    real_decision: str
    counter_decision: str
    reason: str | None
    diff: bool


class WhatIfResponse(BaseModel):
    tenant_id: str
    total_real_events: int
    diff_count: int
    summary: dict
    diffs: list[CounterEvent]


# ---- Helpers ---------------------------------------------------------------


async def _require_membership(
    session: AsyncSession, user: User, tenant_id: str
) -> Membership:
    """Fail with 404 (not 403) if the user has no membership — don't leak existence."""
    stmt = select(Membership).where(
        Membership.user_id == user.id, Membership.tenant_id == tenant_id
    )
    result = await session.execute(stmt)
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    return membership


def _require_role(membership: Membership, allowed: tuple[str, ...]) -> None:
    if membership.role not in allowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"role {membership.role!r} cannot perform this action",
        )


# ---- Routes ----------------------------------------------------------------


@router.get("/{tenant_id}/usage", response_model=UsageOut)
async def get_tenant_usage(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> UsageOut:
    _, user = auth
    await _require_membership(session, user, tenant_id)

    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")

    from datetime import datetime, timezone
    used = await get_usage(tenant_id, redis=None, session=session)
    quota = tenant.monthly_event_quota
    period = datetime.now(tz=timezone.utc).strftime("%Y-%m")
    quota_pct = round(used / quota * 100, 2) if quota != -1 else None
    overage = max(0, used - quota) if quota != -1 else 0
    warn = quota_warning_threshold(quota) if quota != -1 else None

    return UsageOut(
        tenant_id=tenant_id,
        plan=tenant.plan,
        period=period,
        events_used=used,
        quota=quota,
        quota_pct=quota_pct,
        overage=overage,
        warning_threshold=warn,
    )


@router.get("/{tenant_id}/events", response_model=list[EventOut])
async def list_tenant_events(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    conversation_id: str | None = Query(default=None),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> list[EventOut]:
    _, user = auth
    await _require_membership(session, user, tenant_id)

    stmt = select(EventRow).where(EventRow.tenant_id == tenant_id)
    if conversation_id is not None:
        stmt = stmt.where(EventRow.conversation_id == conversation_id)
    if start is not None:
        stmt = stmt.where(EventRow.occurred_at >= start)
    if end is not None:
        stmt = stmt.where(EventRow.occurred_at <= end)
    stmt = stmt.order_by(EventRow.sequence_no.desc()).limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
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


@router.get("/{tenant_id}/keys", response_model=list[KeyOut])
async def list_keys(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> list[KeyOut]:
    _, user = auth
    await _require_membership(session, user, tenant_id)

    stmt = (
        select(ApiKey)
        .where(ApiKey.tenant_id == tenant_id)
        .order_by(ApiKey.created_at.desc())
    )
    result = await session.execute(stmt)
    return [
        KeyOut(
            id=k.id,
            tenant_id=k.tenant_id,
            label=k.label,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
            revoked_at=k.revoked_at,
        )
        for k in result.scalars().all()
    ]


@router.post(
    "/{tenant_id}/keys",
    status_code=status.HTTP_201_CREATED,
    response_model=IssueKeyResponse,
)
async def issue_key(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    body: IssueKeyRequest,
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> IssueKeyResponse:
    _, user = auth
    membership = await _require_membership(session, user, tenant_id)
    _require_role(membership, ("owner", "admin"))

    settings = get_settings()
    raw = f"{settings.api_key_prefix}{secrets.token_urlsafe(32)}"
    key = ApiKey(tenant_id=tenant_id, label=body.label, key_hash=_hash_key(raw))
    session.add(key)
    await session.flush()

    return IssueKeyResponse(
        id=key.id,
        tenant_id=tenant_id,
        label=body.label,
        api_key=raw,
        created_at=key.created_at,
    )


@router.delete(
    "/{tenant_id}/keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_key(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    key_id: uuid.UUID,
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> None:
    _, user = auth
    membership = await _require_membership(session, user, tenant_id)
    _require_role(membership, ("owner", "admin"))

    stmt = select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
    result = await session.execute(stmt)
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "api key not found")

    if key.revoked_at is None:
        await session.execute(
            update(ApiKey)
            .where(ApiKey.id == key.id)
            .values(revoked_at=datetime.now(tz=timezone.utc))
        )


# ---- Compliance packs (session-JWT) ----------------------------------------


@router.get("/{tenant_id}/packs")
async def list_packs(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> dict:
    _, user = auth
    await _require_membership(session, user, tenant_id)
    return {"packs": sorted(PACK_REGISTRY.keys()), "count": len(PACK_REGISTRY)}


@router.post("/{tenant_id}/packs/{regulation}")
async def generate_pack(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    regulation: Annotated[str, Path(pattern=r"^[a-z0-9_]+$")],
    body: PackRequest = Body(default_factory=PackRequest),
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> Response:
    _, user = auth
    await _require_membership(session, user, tenant_id)

    cls = PACK_REGISTRY.get(regulation)
    if cls is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"unknown regulation {regulation!r}; available: {sorted(PACK_REGISTRY)}",
        )

    end = body.end or datetime.now(tz=timezone.utc)
    start = body.start or (end - timedelta(days=30))

    gen = cls(session=session, tenant_id=tenant_id, start=start, end=end)
    await gen.collect()

    if not gen.chain_ok:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "error": "ledger_chain_broken",
                "first_broken_index": gen.chain_broken_at,
                "checked": len(gen.events),
            },
        )

    artifact = gen.build()
    filename = f"goderash-{regulation}-{tenant_id}-{end.date().isoformat()}.zip"
    return Response(
        content=artifact.zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Goderash-Pack-Sha256": artifact.sha256,
            "X-Goderash-Pack-Event-Count": str(artifact.manifest["event_count"]),
            "X-Goderash-Regulation": regulation,
        },
    )


# ---- What-If projection (session-JWT) ---------------------------------------


@router.post("/{tenant_id}/whatif", response_model=WhatIfResponse)
async def whatif_projection(
    tenant_id: Annotated[str, Path(min_length=1, max_length=128)],
    body: WhatIfRequest = Body(default_factory=WhatIfRequest),
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> WhatIfResponse:
    _, user = auth
    await _require_membership(session, user, tenant_id)

    end = body.end or datetime.now(tz=timezone.utc)
    start = body.start or (end - timedelta(days=30))

    ledger = EventLedger(session)
    rows = await ledger.iter_tenant(tenant_id, start=start, end=end)

    policy = WhatIfPolicy(
        velocity_caps=dict(body.policy.velocity_caps),
        velocity_amount_caps=dict(body.policy.velocity_amount_caps),
        deny_tools=tuple(body.policy.deny_tools),
        require_confirmation=tuple(body.policy.require_confirmation),
        new_permission_mode=body.policy.new_permission_mode,
    )
    projector = WhatIfProjector(tenant_id=tenant_id, policy=policy)
    report = projector.project(
        [
            {
                "sequence_no": r.sequence_no,
                "event_type": r.event_type,
                "payload": r.payload,
            }
            for r in rows
        ]
    )

    return WhatIfResponse(
        tenant_id=tenant_id,
        total_real_events=report["total_real_events"],
        diff_count=report["diff_count"],
        summary=report["summary"],
        diffs=[
            CounterEvent(
                sequence_no=d["sequence_no"],
                event_type=d["event_type"],
                tool_name=d.get("tool_name"),
                real_decision=d["real_decision"],
                counter_decision=d["counter_decision"],
                reason=d.get("reason"),
                diff=d["diff"],
            )
            for d in report["diffs"]
        ],
    )
