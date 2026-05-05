"""Outbound webhook dispatcher.

Delivers signed JSON payloads to tenant-registered HTTPS endpoints.
Signing scheme: HMAC-SHA256 of the raw request body, delivered in
    X-Goderash-Signature: sha256=<hex>

Delivery is fire-and-forget (asyncio.create_task). Failures are logged
and written back to WebhookEndpoint.last_status but never surfaced to
the caller.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models.tenant import WebhookEndpoint

log = logging.getLogger(__name__)

# Known webhook event types
EVENT_CHAIN_BROKEN = "chain.broken"
EVENT_QUOTA_WARNING = "quota.warning"
EVENT_QUOTA_EXCEEDED = "quota.exceeded"


def sign_payload(body: bytes, secret: str) -> str:
    """Return the HMAC-SHA256 hex digest of `body` using `secret`."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def dispatch(
    session: AsyncSession,
    tenant_id: str,
    event_type: str,
    payload: dict,
) -> None:
    """Load active endpoints subscribed to `event_type` and deliver in background."""
    stmt = select(WebhookEndpoint).where(
        WebhookEndpoint.tenant_id == tenant_id,
        WebhookEndpoint.is_active == True,  # noqa: E712
    )
    rows = (await session.execute(stmt)).scalars().all()
    targets = [r for r in rows if r.subscribes_to(event_type)]

    if not targets:
        return

    settings = get_settings()
    for endpoint in targets:
        asyncio.create_task(
            _deliver(
                endpoint_id=str(endpoint.id),
                url=endpoint.url,
                secret=endpoint.hmac_secret,
                event_type=event_type,
                payload=payload,
                timeout=settings.webhook_delivery_timeout_seconds,
                max_retries=settings.webhook_max_retries,
                # Pass back a coroutine to update last_status in the same session
                # is not safe across asyncio tasks. Instead we write a separate
                # session inside _deliver.
            ),
            name=f"webhook:{endpoint.id}:{event_type}",
        )


async def _deliver(
    *,
    endpoint_id: str,
    url: str,
    secret: str,
    event_type: str,
    payload: dict,
    timeout: float,
    max_retries: int,
) -> None:
    """POST the signed payload to `url`, retrying on transient failures."""
    from ..db import session_scope  # local import to avoid circular

    envelope = {
        "event_type": event_type,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "data": payload,
    }
    body = json.dumps(envelope, default=str).encode()
    signature = sign_payload(body, secret)
    headers = {
        "Content-Type": "application/json",
        "X-Goderash-Signature": signature,
        "X-Goderash-Event": event_type,
    }

    last_status: int | None = None
    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, content=body, headers=headers)
                last_status = r.status_code
                if r.status_code < 500:
                    break  # 2xx/4xx — stop retrying
                log.warning(
                    "webhook.deliver.retrying",
                    endpoint_id=endpoint_id,
                    status=r.status_code,
                    attempt=attempt,
                )
        except Exception as exc:
            log.warning(
                "webhook.deliver.error",
                endpoint_id=endpoint_id,
                error=str(exc),
                attempt=attempt,
            )

    # Update last_status in a fresh session (original session may be closed).
    try:
        async with session_scope() as s:
            from uuid import UUID
            stmt = select(WebhookEndpoint).where(
                WebhookEndpoint.id == UUID(endpoint_id)
            )
            ep = (await s.execute(stmt)).scalar_one_or_none()
            if ep is not None:
                ep.last_fired_at = datetime.now(tz=timezone.utc)
                ep.last_status = last_status
    except Exception as exc:
        log.warning("webhook.deliver.status_update_failed", error=str(exc))
