"""Append-only event ledger.

Properties:
- Rows are never updated after insert.
- Per-tenant monotonic sequence via `sequence_no`.
- Hash chain computed under an advisory lock so two concurrent appends
  can't produce siblings with the same prev_hash.
- Idempotent on `event_id` (unique index): retries at the SDK are safe.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..events.types import GoderashEventEnvelope
from ..models.event import EventRow
from .chain import GENESIS_PREV_HASH, canonical_json, compute_hash


class LedgerAppendError(Exception):
    """Raised when an append cannot be performed (e.g. tenant advisory lock busy)."""


class EventLedger:
    """Durable append-only log of GoderashEventEnvelopes.

    One instance per request is typical; holds no state of its own.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append_many(
        self,
        tenant_id: str,
        envelopes: Sequence[GoderashEventEnvelope],
    ) -> list[GoderashEventEnvelope]:
        """Append a batch as one transaction under a per-tenant advisory lock.

        Returns the envelopes with `hash`, `prev_hash`, and `recorded_at`
        populated.
        """
        if not envelopes:
            return []

        # Advisory lock scoped to this tenant: serializes hash-chain extension.
        lock_key = _tenant_lock_key(tenant_id)
        await self._session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})

        prev_hash = await self._fetch_head_hash(tenant_id)

        stored: list[GoderashEventEnvelope] = []
        rows_to_insert: list[dict] = []
        now = datetime.now(tz=timezone.utc)

        # Use the max sequence_no already persisted as our starting point.
        next_seq = await self._fetch_head_sequence(tenant_id) + 1

        for env in envelopes:
            if env.tenant_id != tenant_id:
                raise LedgerAppendError(
                    f"envelope.tenant_id ({env.tenant_id}) != append tenant ({tenant_id})"
                )

            payload_dict = env.payload.model_dump(mode="json")
            event_hash = compute_hash(prev_hash, payload_dict)

            sealed = env.model_copy(
                update={
                    "prev_hash": prev_hash,
                    "hash": event_hash,
                    "recorded_at": now,
                }
            )
            stored.append(sealed)

            rows_to_insert.append(
                {
                    "event_id": sealed.event_id,
                    "tenant_id": sealed.tenant_id,
                    "agent_id": sealed.agent_id,
                    "conversation_id": sealed.conversation_id,
                    "turn_id": sealed.turn_id,
                    "parent_event_id": sealed.parent_event_id,
                    "sequence_no": next_seq,
                    "schema_version": sealed.schema_version,
                    "event_type": sealed.payload.event_type,
                    "occurred_at": sealed.occurred_at,
                    "recorded_at": sealed.recorded_at,
                    "payload": payload_dict,
                    "payload_canonical": canonical_json(payload_dict),
                    "prev_hash": prev_hash,
                    "hash": event_hash,
                }
            )

            prev_hash = event_hash
            next_seq += 1

        # Idempotent insert: dup on event_id is a silent no-op.
        stmt = pg_insert(EventRow).values(rows_to_insert).on_conflict_do_nothing(
            index_elements=["event_id"]
        )
        await self._session.execute(stmt)

        return stored

    async def _fetch_head_hash(self, tenant_id: str) -> str:
        stmt = (
            select(EventRow.hash)
            .where(EventRow.tenant_id == tenant_id)
            .order_by(EventRow.sequence_no.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return row if row is not None else GENESIS_PREV_HASH

    async def _fetch_head_sequence(self, tenant_id: str) -> int:
        stmt = (
            select(EventRow.sequence_no)
            .where(EventRow.tenant_id == tenant_id)
            .order_by(EventRow.sequence_no.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return int(row) if row is not None else 0

    async def iter_tenant(
        self,
        tenant_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[EventRow]:
        """Return events for a tenant in chain order."""
        stmt = select(EventRow).where(EventRow.tenant_id == tenant_id)
        if start is not None:
            stmt = stmt.where(EventRow.occurred_at >= start)
        if end is not None:
            stmt = stmt.where(EventRow.occurred_at <= end)
        stmt = stmt.order_by(EventRow.sequence_no.asc())
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())


def _tenant_lock_key(tenant_id: str) -> int:
    """Stable 63-bit int hash of a tenant id for pg_advisory_xact_lock."""
    import hashlib

    digest = hashlib.blake2b(tenant_id.encode("utf-8"), digest_size=8).digest()
    # Truncate to 63 bits so it fits in a signed bigint.
    return int.from_bytes(digest, "big") & 0x7FFF_FFFF_FFFF_FFFF
