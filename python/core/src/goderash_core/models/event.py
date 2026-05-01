"""`events` — the append-only ledger table."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sequence_no", name="uq_events_tenant_sequence"),
        UniqueConstraint("tenant_id", "hash", name="uq_events_tenant_hash"),
        Index("ix_events_tenant_occurred_at", "tenant_id", "occurred_at"),
        Index("ix_events_tenant_conversation", "tenant_id", "conversation_id"),
        Index("ix_events_tenant_event_type", "tenant_id", "event_type"),
    )

    # Identity
    event_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    turn_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_event_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    # Ordering within a tenant
    sequence_no: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Schema + type
    schema_version: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # Timestamps
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Payload — both structured and canonical form (canonical is what we hash)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_canonical: Mapped[str] = mapped_column(Text, nullable=False)

    # Hash chain
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
