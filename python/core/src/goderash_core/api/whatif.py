"""What-If counterfactual replay endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import session_scope
from ..ledger.store import EventLedger
from ..whatif import WhatIfPolicy, WhatIfProjector
from .auth import AuthContext, require_api_key

router = APIRouter(prefix="/v1/whatif", tags=["whatif"])


class PolicyIn(BaseModel):
    velocity_caps: dict[str, int] = Field(default_factory=dict)
    velocity_amount_caps: dict[str, float] = Field(default_factory=dict)
    deny_tools: list[str] = Field(default_factory=list)
    require_confirmation: list[str] = Field(default_factory=list)
    new_permission_mode: Literal["plan", "default", "auto", "strict"] | None = None


class WhatIfRequest(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    policy: PolicyIn = Field(default_factory=PolicyIn)


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


async def _session() -> AsyncSession:
    async with session_scope() as s:
        yield s


@router.post("", response_model=WhatIfResponse)
async def project(
    body: WhatIfRequest = Body(...),
    auth: AuthContext = Depends(require_api_key),
    session: AsyncSession = Depends(_session),
) -> WhatIfResponse:
    end = body.end or datetime.now(tz=timezone.utc)
    start = body.start or (end - timedelta(days=30))

    ledger = EventLedger(session)
    rows = await ledger.iter_tenant(auth.tenant_id, start=start, end=end)

    policy = WhatIfPolicy(
        velocity_caps=dict(body.policy.velocity_caps),
        velocity_amount_caps=dict(body.policy.velocity_amount_caps),
        deny_tools=tuple(body.policy.deny_tools),
        require_confirmation=tuple(body.policy.require_confirmation),
        new_permission_mode=body.policy.new_permission_mode,
    )
    projector = WhatIfProjector(tenant_id=auth.tenant_id, policy=policy)
    report = projector.project(
        [
            {
                "sequence_no": r.sequence_no,
                "event_type": r.event_type,
                "occurred_at": r.occurred_at,
                "payload": r.payload,
            }
            for r in rows
        ]
    )

    return WhatIfResponse(
        tenant_id=report.tenant_id,
        total_real_events=report.total_real_events,
        diff_count=len(report.diffs),
        summary=report.summary(),
        diffs=[
            CounterEvent(
                sequence_no=d.sequence_no,
                event_type=d.event_type,
                tool_name=d.tool_name,
                real_decision=d.real_decision,
                counter_decision=d.counter_decision,
                reason=d.reason,
                diff=d.diff,
            )
            for d in report.diffs
        ],
    )
