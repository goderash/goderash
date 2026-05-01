"""Eval fixtures — the canonical 7-event golden-path turn from the README.

These payloads, dates, and conversation IDs are *frozen*. Any change here
breaks every eval below — that is intentional. The hash chain is a
regression sensor: if we silently re-canonicalize a payload, evals fail.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from goderash_core.ledger.chain import GENESIS_PREV_HASH, compute_hash

GOLDEN_TENANT = "demo"
GOLDEN_AGENT = "ops-v1"
GOLDEN_CONVERSATION = "c-golden"
GOLDEN_TURN = "t-golden"
GOLDEN_TIMESTAMP = datetime(2026, 4, 29, 12, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class GoldenEvent:
    """A frozen ledger row — enough to feed verify_chain and pack renderers."""

    sequence_no: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime
    prev_hash: str
    hash: str
    conversation_id: str = GOLDEN_CONVERSATION


# Payload definitions kept short and deterministic. Order matters — this is the
# canonical turn shape: started → llm → tool → permission → tool.completed →
# llm.completed → turn.completed.
_GOLDEN_PAYLOADS: list[dict[str, Any]] = [
    {
        "event_type": "agent.turn.started",
        "user_message": "transfer $500 from checking to savings",
    },
    {
        "event_type": "llm.call.started",
        "provider": "anthropic",
        "model": "claude-opus-4-7",
    },
    {
        "event_type": "tool.invoked",
        "tool_name": "transfer_money",
        "tool_category": "action",
        "input_args_hash": "a" * 64,
    },
    {
        "event_type": "permission.granted",
        "tool_name": "transfer_money",
        "tool_category": "action",
        "source": "user",
    },
    {
        "event_type": "tool.completed",
        "tool_name": "transfer_money",
        "success": True,
        "duration_ms": 42,
        "result_hash": "b" * 64,
    },
    {
        "event_type": "llm.call.completed",
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "input_tokens": 120,
        "output_tokens": 38,
        "duration_ms": 700,
        "stop_reason": "end_turn",
    },
    {
        "event_type": "agent.turn.completed",
        "assistant_message": "transferred $500",
        "input_tokens": 120,
        "output_tokens": 38,
        "tool_calls_made": 1,
        "duration_ms": 800,
        "stop_reason": "end_turn",
    },
]


def _build_golden_chain() -> list[GoldenEvent]:
    out: list[GoldenEvent] = []
    prev = GENESIS_PREV_HASH
    for i, payload in enumerate(_GOLDEN_PAYLOADS, start=1):
        h = compute_hash(prev, payload)
        out.append(
            GoldenEvent(
                sequence_no=i,
                event_type=payload["event_type"],
                payload=payload,
                occurred_at=GOLDEN_TIMESTAMP,
                prev_hash=prev,
                hash=h,
            )
        )
        prev = h
    return out


@pytest.fixture(scope="session")
def golden_chain() -> Sequence[GoldenEvent]:
    """The canonical 7-event golden-path turn."""
    return _build_golden_chain()


@pytest.fixture(scope="session")
def golden_chain_dicts(golden_chain: Sequence[GoldenEvent]) -> list[dict[str, Any]]:
    """Golden chain shaped as `verify_chain` expects."""
    return [
        {"prev_hash": e.prev_hash, "hash": e.hash, "payload": e.payload}
        for e in golden_chain
    ]
