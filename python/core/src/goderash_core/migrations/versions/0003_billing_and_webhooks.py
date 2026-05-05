"""billing columns on tenants + webhook_endpoints table

Revision ID: 0003_billing_and_webhooks
Revises: 0002_users_and_memberships
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_billing_and_webhooks"
down_revision = "0002_users_and_memberships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── billing columns on tenants ─────────────────────────────────────────
    op.add_column("tenants", sa.Column("plan", sa.String(32), nullable=False, server_default="hobby"))
    op.add_column("tenants", sa.Column("monthly_event_quota", sa.Integer(), nullable=False, server_default="10000"))
    op.add_column("tenants", sa.Column("stripe_customer_id", sa.String(128), nullable=True))
    op.add_column("tenants", sa.Column("stripe_subscription_id", sa.String(128), nullable=True))

    # ── webhook_endpoints ──────────────────────────────────────────────────
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(128),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("hmac_secret", sa.String(64), nullable=False),
        sa.Column("events_filter", sa.String(512), nullable=False, server_default="chain.broken"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.Integer(), nullable=True),
    )
    op.create_index("ix_webhook_endpoints_tenant_id", "webhook_endpoints", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_webhook_endpoints_tenant_id", table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
    op.drop_column("tenants", "stripe_subscription_id")
    op.drop_column("tenants", "stripe_customer_id")
    op.drop_column("tenants", "monthly_event_quota")
    op.drop_column("tenants", "plan")
