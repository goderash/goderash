"""Stripe customer and subscription management.

All Stripe calls are fire-and-optional: if billing is disabled or Stripe
raises, we log and continue. The audit ledger must never fail to accept events
because of a billing service outage.
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)

_PLAN_TO_PRICE: dict[str, str | None] = {
    "hobby": None,       # free — no subscription
    "startup": None,     # populated from settings at runtime
    "growth": None,
    "enterprise": None,  # manual / custom
}


def _stripe_module():  # pragma: no cover
    """Lazy import so missing stripe SDK never crashes the server."""
    try:
        import stripe  # type: ignore[import-untyped]
        return stripe
    except ImportError:
        return None


async def create_stripe_customer(
    *,
    email: str,
    display_name: str,
    tenant_id: str,
    stripe_secret_key: str,
) -> str | None:
    """Create a Stripe customer and return the customer ID."""
    stripe = _stripe_module()
    if stripe is None:
        log.warning("billing.stripe.missing_sdk")
        return None

    try:
        customer = await asyncio.to_thread(
            stripe.Customer.create,
            api_key=stripe_secret_key,
            email=email,
            name=display_name,
            metadata={"tenant_id": tenant_id},
        )
        return customer["id"]
    except Exception as exc:
        log.warning("billing.stripe.customer_create_failed", error=str(exc))
        return None


async def create_stripe_subscription(
    *,
    customer_id: str,
    plan: str,
    stripe_secret_key: str,
    price_id: str | None,
) -> str | None:
    """Create a Stripe subscription for the given plan and return the subscription ID."""
    if price_id is None:
        return None  # free plan or price not configured

    stripe = _stripe_module()
    if stripe is None:
        return None

    try:
        sub = await asyncio.to_thread(
            stripe.Subscription.create,
            api_key=stripe_secret_key,
            customer=customer_id,
            items=[{"price": price_id}],
            metadata={"plan": plan},
        )
        return sub["id"]
    except Exception as exc:
        log.warning("billing.stripe.subscription_create_failed", plan=plan, error=str(exc))
        return None


async def report_stripe_usage(
    *,
    subscription_item_id: str,
    quantity: int,
    stripe_secret_key: str,
) -> None:
    """Report metered usage to Stripe for overage billing."""
    stripe = _stripe_module()
    if stripe is None:
        return

    try:
        await asyncio.to_thread(
            stripe.SubscriptionItem.create_usage_record,
            subscription_item_id,
            api_key=stripe_secret_key,
            quantity=quantity,
            action="set",
        )
    except Exception as exc:
        log.warning("billing.stripe.usage_report_failed", error=str(exc))
