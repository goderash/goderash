"""All registered packs build correctly given a known-good ledger fixture."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from goderash_core.ledger.chain import GENESIS_PREV_HASH, compute_hash
from goderash_core.packs import PACK_REGISTRY


def _row(event_type: str, payload: dict, prev_hash: str = GENESIS_PREV_HASH) -> MagicMock:
    row = MagicMock()
    row.event_id = uuid4()
    row.event_type = event_type
    row.payload = payload
    row.occurred_at = datetime.now(tz=timezone.utc)
    row.conversation_id = "c1"
    row.sequence_no = 1
    row.prev_hash = prev_hash
    row.hash = compute_hash(prev_hash, payload)
    return row


@pytest.mark.parametrize("regulation", sorted(PACK_REGISTRY.keys()))
@pytest.mark.asyncio
async def test_pack_builds(regulation: str) -> None:
    cls = PACK_REGISTRY[regulation]

    # Build a fresh chain of representative events.
    payloads = [
        {"event_type": "agent.turn.started", "user_message": "hi"},
        {
            "event_type": "permission.granted",
            "tool_name": "balance",
            "source": "rule",
        },
        {
            "event_type": "tool.completed",
            "tool_name": "balance",
            "success": True,
            "duration_ms": 5,
            "result_hash": "a" * 64,
        },
    ]
    rows = []
    prev = GENESIS_PREV_HASH
    for p in payloads:
        r = _row(p["event_type"], p, prev)
        rows.append(r)
        prev = r.hash

    session = MagicMock()
    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=exec_result)

    end = datetime.now(tz=timezone.utc)
    gen = cls(session=session, tenant_id="t", start=end - timedelta(days=1), end=end)
    await gen.collect()
    assert gen.chain_ok, f"chain broke at index {gen.chain_broken_at}"

    artifact = gen.build()
    assert artifact.regulation == regulation
    assert artifact.manifest["event_count"] == len(rows)
    assert artifact.zip_bytes
    assert len(artifact.sha256) == 64
