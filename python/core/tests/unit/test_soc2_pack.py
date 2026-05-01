"""Smoke test for the SOC2 pack generator's shape."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from goderash_core.ledger.chain import GENESIS_PREV_HASH, canonical_json, compute_hash
from goderash_core.packs.soc2 import Soc2PackGenerator


def _row(
    event_type: str,
    payload: dict,
    *,
    prev_hash: str = GENESIS_PREV_HASH,
) -> MagicMock:
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


@pytest.mark.asyncio
async def test_soc2_pack_builds() -> None:
    session = MagicMock()

    # Build two chained rows so verify_chain succeeds.
    payload1 = {
        "event_type": "permission.granted",
        "tool_name": "check_balance",
        "source": "rule",
    }
    payload2 = {
        "event_type": "tool.completed",
        "tool_name": "check_balance",
        "success": True,
        "duration_ms": 10,
        "result_hash": "a" * 64,
    }
    r1 = _row("permission.granted", payload1)
    r2 = _row("tool.completed", payload2, prev_hash=r1.hash)

    # Ensure canonical payloads match what the chain expected.
    assert compute_hash(GENESIS_PREV_HASH, payload1) == r1.hash
    assert compute_hash(r1.hash, payload2) == r2.hash
    assert canonical_json(payload1) is not None

    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = [r1, r2]
    session.execute = AsyncMock(return_value=exec_result)

    gen = Soc2PackGenerator(
        session=session,
        tenant_id="demo",
        start=datetime.now(tz=timezone.utc) - timedelta(days=1),
        end=datetime.now(tz=timezone.utc),
    )
    await gen.collect()
    assert gen.chain_ok is True

    artifact = gen.build()
    assert artifact.regulation == "soc2"
    assert artifact.manifest["event_count"] == 2
    assert artifact.zip_bytes
    assert artifact.sha256
