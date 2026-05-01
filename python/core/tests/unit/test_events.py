"""Round-trip serialization of every event type in the discriminated union."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from goderash_core.events.types import (
    AgentTurnCompleted,
    AgentTurnStarted,
    ContractViolated,
    LLMCallCompleted,
    LLMCallStarted,
    PermissionDenied,
    PermissionGranted,
    ToolCompleted,
    ToolFailed,
    ToolInvoked,
    GoderashEventEnvelope,
)


@pytest.mark.parametrize(
    "payload",
    [
        AgentTurnStarted(user_message="hi"),
        AgentTurnCompleted(
            assistant_message="hello",
            input_tokens=10,
            output_tokens=5,
            tool_calls_made=0,
            duration_ms=42,
            stop_reason="end_turn",
        ),
        ToolInvoked(
            tool_name="check_balance",
            tool_category="query",
            input_args_hash="a" * 64,
        ),
        ToolCompleted(
            tool_name="check_balance",
            success=True,
            duration_ms=10,
            result_hash="b" * 64,
        ),
        ToolFailed(
            tool_name="check_balance",
            error_class="TimeoutError",
            error_message="upstream timeout",
            duration_ms=5000,
        ),
        LLMCallStarted(provider="anthropic", model="claude-opus-4-7"),
        LLMCallCompleted(
            provider="anthropic",
            model="claude-opus-4-7",
            input_tokens=100,
            output_tokens=50,
            duration_ms=1200,
        ),
        PermissionGranted(tool_name="transfer_money", source="user"),
        PermissionDenied(tool_name="transfer_money", source="velocity", reason="daily cap"),
        ContractViolated(
            contract_id="daily_transfer_cap",
            contract_version="1.0.0",
            clause="amount <= 10000",
            severity="critical",
        ),
    ],
)
def test_event_roundtrip(payload: object) -> None:
    env = GoderashEventEnvelope(
        tenant_id="t1",
        agent_id="a1",
        conversation_id="c1",
        turn_id="u1",
        occurred_at=datetime.now(tz=timezone.utc),
        payload=payload,  # type: ignore[arg-type]
    )

    as_json = env.model_dump_json()
    parsed = GoderashEventEnvelope.model_validate(json.loads(as_json))
    assert parsed == env
