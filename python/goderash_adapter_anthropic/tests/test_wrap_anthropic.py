"""Unit tests for the Anthropic adapter.

All tests run without a real Anthropic API key or Goderash control plane.
The SDK client is created with a stub endpoint and never flushed; we
inspect the buffer directly to assert events were emitted in the right order
with the right fields.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from goderash_sdk import GoderashClient, GoderashContext
from goderash_adapter_anthropic import audit_messages_response, wrap_anthropic


@pytest.fixture
def client_and_ctx() -> tuple[GoderashClient, GoderashContext]:
    gdr = GoderashClient(api_key="gdr_test", tenant="test", endpoint="http://localhost:9")
    ctx = gdr.new_context()
    return gdr, ctx


def _drain(gdr: GoderashClient) -> list[dict]:
    with gdr._state.lock:
        events = list(gdr._state.buffer)
        gdr._state.buffer.clear()
    return [vars(e) for e in events]


def _make_response(
    *,
    model: str = "claude-opus-4-7",
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 5,
    tool_use_blocks: list[dict] | None = None,
) -> Any:
    content = []
    for block in tool_use_blocks or []:
        content.append(
            SimpleNamespace(type="tool_use", name=block["name"], input=block.get("input", {}))
        )
    return SimpleNamespace(
        model=model,
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            model_dump=lambda: {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        ),
        content=content,
    )


class TestAuditMessagesResponse:
    def test_emits_llm_call_completed(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        response = _make_response(input_tokens=100, output_tokens=20)
        audit_messages_response(gdr, ctx, response, provider="anthropic", model="claude-opus-4-7")
        payloads = [e["payload"] for e in _drain(gdr)]

        assert any(p.event_type == "llm.call.completed" for p in payloads)
        completed = next(p for p in payloads if p.event_type == "llm.call.completed")
        assert completed.input_tokens == 100
        assert completed.output_tokens == 20

    def test_emits_tool_invoked_per_tool_use_block(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        response = _make_response(
            tool_use_blocks=[
                {"name": "check_balance", "input": {"account": "savings"}},
                {"name": "transfer_money", "input": {"amount": 100}},
            ]
        )
        audit_messages_response(gdr, ctx, response)
        payloads = [e["payload"] for e in _drain(gdr)]
        tool_events = [p for p in payloads if p.event_type == "tool.invoked"]
        assert len(tool_events) == 2
        names = {p.tool_name for p in tool_events}
        assert names == {"check_balance", "transfer_money"}

    def test_no_tool_invoked_on_text_only_response(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        response = _make_response()
        audit_messages_response(gdr, ctx, response)
        payloads = [e["payload"] for e in _drain(gdr)]
        assert not any(p.event_type == "tool.invoked" for p in payloads)

    def test_tool_invoked_has_stable_hash_for_same_input(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        input_data = {"amount": 100, "account": "savings"}
        response = _make_response(tool_use_blocks=[{"name": "transfer_money", "input": input_data}])
        audit_messages_response(gdr, ctx, response)
        payloads = [e["payload"] for e in _drain(gdr)]
        tool_event = next(p for p in payloads if p.event_type == "tool.invoked")

        # Same input dict → same hash both times.
        response2 = _make_response(tool_use_blocks=[{"name": "transfer_money", "input": input_data}])
        audit_messages_response(gdr, ctx, response2)
        payloads2 = [e["payload"] for e in _drain(gdr)]
        tool_event2 = next(p for p in payloads2 if p.event_type == "tool.invoked")
        assert tool_event.input_args_hash == tool_event2.input_args_hash

    def test_stop_reason_forwarded(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        response = _make_response(stop_reason="max_tokens")
        audit_messages_response(gdr, ctx, response)
        payloads = [e["payload"] for e in _drain(gdr)]
        completed = next(p for p in payloads if p.event_type == "llm.call.completed")
        assert completed.stop_reason == "max_tokens"


class TestWrapAnthropic:
    def test_wrap_replaces_create_method(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        fake_anthropic = MagicMock()
        original_create = fake_anthropic.messages.create
        wrap_anthropic(fake_anthropic, goderash=gdr, context=ctx)
        assert fake_anthropic.messages.create is not original_create
        assert fake_anthropic.messages._goderash_orig_create is original_create

    def test_wrap_emits_started_and_completed(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        response = _make_response(input_tokens=50, output_tokens=10)
        fake_anthropic = MagicMock()
        fake_anthropic.messages.create.return_value = response
        wrap_anthropic(fake_anthropic, goderash=gdr, context=ctx)
        fake_anthropic.messages.create(model="claude-opus-4-7", messages=[])
        payloads = [e["payload"] for e in _drain(gdr)]
        event_types = [p.event_type for p in payloads]
        assert "llm.call.started" in event_types
        assert "llm.call.completed" in event_types
