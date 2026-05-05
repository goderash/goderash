"""`tenants`, `api_keys`, and `webhook_endpoints`."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# ---------------------------------------------------------------------------
# Plan constants — mirrors product.ts pricing tiers
# ---------------------------------------------------------------------------
PLAN_HOBBY = "hobby"
PLAN_STARTUP = "startup"
PLAN_GROWTH = "growth"
PLAN_ENTERPRISE = "enterprise"

PLAN_QUOTAS: dict[str, int] = {
    PLAN_HOBBY: 10_000,
    PLAN_STARTUP: 1_000_000,
    PLAN_GROWTH: 10_000_000,
    PLAN_ENTERPRISE: -1,  # unlimited
}

PLAN_OVERAGE_RATE_PER_1K: dict[str, float | None] = {
    PLAN_HOBBY: None,       # hard block — no overage billing
    PLAN_STARTUP: 0.10,
    PLAN_GROWTH: 0.08,
    PLAN_ENTERPRISE: None,  # custom contract
}


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Billing
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default=PLAN_HOBBY)
    monthly_event_quota: Mapped[int] = mapped_column(
        Integer, nullable=False, default=PLAN_QUOTAS[PLAN_HOBBY]
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True)


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_tenant_id", "tenant_id"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256 hash of the raw key — raw key is never persisted.
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebhookEndpoint(Base):
    """Registered HTTPS endpoint that receives signed event notifications."""

    __tablename__ = "webhook_endpoints"
    __table_args__ = (Index("ix_webhook_endpoints_tenant_id", "tenant_id"),)

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # HMAC-SHA256 secret shown to the user once at creation; never returned again.
    hmac_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    # Comma-separated event filter, e.g. "chain.broken,quota.warning"
    events_filter: Mapped[str] = mapped_column(
        String(512), nullable=False, default="chain.broken"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @staticmethod
    def generate_secret() -> str:
        return secrets.token_hex(32)

    def subscribes_to(self, event_type: str) -> bool:
        return event_type in {e.strip() for e in self.events_filter.split(",")}
