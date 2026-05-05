"""Billing API routes.

GET  /v1/billing/usage          — current period event count + quota for authed tenant
POST /v1/billing/stripe-webhook — Stripe webhook handler (invoice, subscription events)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..api.auth import AuthContext, require_api_key
from ..billing.usage import get_usage, is_quota_exceeded, quota_warning_threshold
from ..config import get_settings
from ..db import session_scope
from ..models.tenant import PLAN_QUOTAS, Tenant

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/billing", tags=["billing"])


# ── Dependencies ─────────────────────────────────────────────────────────────

async def _session():
    async with session_scope() as s:
        yield s


async def _redis() -> aioredis.Redis | None:
    settings = get_settings()
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.ping()
        return r
    except Exception:
        return None


# ── Schemas ───────────────────────────────────────────────────────────────────

class UsageResponse(BaseModel):
    tenant_id: str
    plan: str
    period: str                  # "YYYY-MM"
    events_used: int
    quota: int                   # -1 = unlimited
    quota_pct: float | None      # None when unlimited
    overage: int                 # events above included quota (0 for hobby/enterprise)
    warning_threshold: int | None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/usage", response_model=UsageResponse)
async def get_billing_usage(
    auth: AuthContext = Depends(require_api_key),
    session: AsyncSession = Depends(_session),
    redis: aioredis.Redis | None = Depends(_redis),
) -> UsageResponse:
    stmt = select(Tenant).where(Tenant.id == auth.tenant_id)
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tenant not found")

    used = await get_usage(auth.tenant_id, redis=redis, session=session)
    quota = tenant.monthly_event_quota
    period = datetime.now(tz=timezone.utc).strftime("%Y-%m")

    quota_pct: float | None = None
    if quota != -1:
        quota_pct = round(used / quota * 100, 2)

    overage = max(0, used - quota) if quota != -1 else 0
    warn = quota_warning_threshold(quota) if quota != -1 else None

    return UsageResponse(
        tenant_id=auth.tenant_id,
        plan=tenant.plan,
        period=period,
        events_used=used,
        quota=quota,
        quota_pct=quota_pct,
        overage=overage,
        warning_threshold=warn,
    )


@router.post("/stripe-webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
    session: AsyncSession = Depends(_session),
) -> dict:
    """Receive Stripe webhook events and update subscription state."""
    settings = get_settings()
    raw_body = await request.body()

    # Verify signature when webhook secret is configured.
    if settings.stripe_webhook_secret:
        if stripe_signature is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing stripe-signature header")
        try:
            import stripe as stripe_sdk  # type: ignore[import-untyped]
            event = stripe_sdk.Webhook.construct_event(
                raw_body, stripe_signature, settings.stripe_webhook_secret
            )
        except Exception as exc:
            log.warning("billing.stripe.webhook_verification_failed", error=str(exc))
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid stripe signature")
    else:
        import json
        event = json.loads(raw_body)

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type == "customer.subscription.updated":
        await _handle_subscription_updated(session, data)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(session, data)

    return {"received": True}


async def _handle_subscription_updated(session: AsyncSession, sub: dict) -> None:
    customer_id = sub.get("customer")
    sub_id = sub.get("id")
    plan = sub.get("metadata", {}).get("plan", "hobby")

    stmt = select(Tenant).where(Tenant.stripe_customer_id == customer_id)
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return

    tenant.plan = plan
    tenant.stripe_subscription_id = sub_id
    tenant.monthly_event_quota = PLAN_QUOTAS.get(plan, PLAN_QUOTAS["hobby"])
    log.info("billing.subscription.updated", tenant_id=tenant.id, plan=plan)


async def _handle_subscription_deleted(session: AsyncSession, sub: dict) -> None:
    customer_id = sub.get("customer")

    stmt = select(Tenant).where(Tenant.stripe_customer_id == customer_id)
    result = await session.execute(stmt)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return

    tenant.plan = "hobby"
    tenant.stripe_subscription_id = None
    tenant.monthly_event_quota = PLAN_QUOTAS["hobby"]
    log.info("billing.subscription.cancelled", tenant_id=tenant.id)
