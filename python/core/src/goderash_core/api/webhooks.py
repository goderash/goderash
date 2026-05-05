"""Webhook endpoint management.

GET    /v1/orgs/{tenant_id}/webhooks             — list endpoints
POST   /v1/orgs/{tenant_id}/webhooks             — register endpoint
DELETE /v1/orgs/{tenant_id}/webhooks/{webhook_id} — deactivate endpoint

Webhook endpoints are available on Startup+ plans. Hobby tenants get a 402.
Requires a session JWT (same auth as /v1/orgs/.../keys).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import session_scope
from ..models.tenant import PLAN_HOBBY, Tenant, WebhookEndpoint
from ..models.user import Membership, User
from ..security.tokens import SessionClaims
from .auth_public import require_session

router = APIRouter(prefix="/v1/orgs", tags=["webhooks"])


async def _session():
    async with session_scope() as s:
        yield s


async def _require_membership(
    session: AsyncSession, user: User, tenant_id: str
) -> Membership:
    """404 (not 403) when the user has no membership — avoid leaking tenant existence."""
    stmt = select(Membership).where(
        Membership.user_id == user.id, Membership.tenant_id == tenant_id
    )
    result = await session.execute(stmt)
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")
    return membership


# ── Schemas ───────────────────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    url: HttpUrl
    events_filter: str = "chain.broken"


class WebhookOut(BaseModel):
    id: str
    tenant_id: str
    url: str
    events_filter: str
    is_active: bool
    created_at: datetime
    last_fired_at: datetime | None
    last_status: int | None


class WebhookCreated(WebhookOut):
    hmac_secret: str  # returned only once at creation


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{tenant_id}/webhooks", response_model=list[WebhookOut])
async def list_webhooks(
    tenant_id: str,
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> list[WebhookOut]:
    _, user = auth
    await _require_membership(session, user, tenant_id)
    stmt = (
        select(WebhookEndpoint)
        .where(WebhookEndpoint.tenant_id == tenant_id)
        .order_by(WebhookEndpoint.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_out(r) for r in rows]


@router.post(
    "/{tenant_id}/webhooks",
    status_code=status.HTTP_201_CREATED,
    response_model=WebhookCreated,
)
async def create_webhook(
    tenant_id: str,
    body: WebhookCreate,
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> WebhookCreated:
    _, user = auth
    await _require_membership(session, user, tenant_id)

    tenant = (
        await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    ).scalar_one_or_none()
    if tenant is None or tenant.plan == PLAN_HOBBY:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "Webhook endpoints require a Startup or higher plan.",
        )

    secret = WebhookEndpoint.generate_secret()
    endpoint = WebhookEndpoint(
        tenant_id=tenant_id,
        url=str(body.url),
        hmac_secret=secret,
        events_filter=body.events_filter,
    )
    session.add(endpoint)
    await session.flush()

    return WebhookCreated(
        id=str(endpoint.id),
        tenant_id=tenant_id,
        url=str(body.url),
        hmac_secret=secret,
        events_filter=body.events_filter,
        is_active=True,
        created_at=endpoint.created_at,
        last_fired_at=None,
        last_status=None,
    )


@router.delete(
    "/{tenant_id}/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_webhook(
    tenant_id: str,
    webhook_id: UUID,
    auth: tuple[SessionClaims, User] = Depends(require_session),
    session: AsyncSession = Depends(_session),
) -> None:
    _, user = auth
    await _require_membership(session, user, tenant_id)

    stmt = select(WebhookEndpoint).where(
        WebhookEndpoint.id == webhook_id,
        WebhookEndpoint.tenant_id == tenant_id,
    )
    endpoint = (await session.execute(stmt)).scalar_one_or_none()
    if endpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook endpoint not found")

    endpoint.is_active = False


def _to_out(r: WebhookEndpoint) -> WebhookOut:
    return WebhookOut(
        id=str(r.id),
        tenant_id=r.tenant_id,
        url=r.url,
        events_filter=r.events_filter,
        is_active=r.is_active,
        created_at=r.created_at,
        last_fired_at=r.last_fired_at,
        last_status=r.last_status,
    )
