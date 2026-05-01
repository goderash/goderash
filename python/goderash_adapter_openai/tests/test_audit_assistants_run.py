"""Unit tests for the OpenAI Assistants adapter.

All tests run without a real OpenAI API key. The OpenAI client is stubbed
at the `beta.threads.runs.steps.list` level; we inspect the Goderash buffer.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from goderash_sdk import GoderashClient, GoderashContext
from goderash_adapter_openai import audit_assistants_run


@pytest.fixture
def client_and_ctx() -> tuple[GoderashClient, GoderashContext]:
    gdr = GoderashClient(api_key="gdr_test", tenant="test", endpoint="http://localhost:9")
    ctx = gdr.new_context()
    return gdr, ctx


def _drain(gdr: GoderashClient) -> list[object]:
    with gdr._state.lock:
        events = list(gdr._state.buffer)
        gdr._state.buffer.clear()
    return [e.payload for e in events]


def _make_openai(*, steps: list[dict]) -> MagicMock:
    """Build a minimal OpenAI stub whose steps.list returns the given steps."""
    step_objects = []
    for s in steps:
        calls = []
        for c in s.get("tool_calls", []):
            fn = SimpleNamespace(
                name=c.get("name", "unknown"),
                arguments=c.get("arguments", "{}"),
                output=c.get("output"),
            )
            calls.append(SimpleNamespace(type=c.get("type", "function"), function=fn, id=c.get("id", "x")))
        detail = SimpleNamespace(tool_calls=calls)
        step_objects.append(SimpleNamespace(type="tool_calls", step_details=detail))

    list_resp = SimpleNamespace(data=step_objects)
    openai = MagicMock()
    openai.beta.threads.runs.steps.list.return_value = list_resp
    return openai


def _make_run(status: str = "completed") -> MagicMock:
    run = MagicMock()
    run.id = "run_abc"
    run.status = status
    return run


class TestAuditAssistantsRun:
    def test_emits_tool_invoked_and_completed_for_function_call(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        openai = _make_openai(steps=[{
            "tool_calls": [{"name": "check_balance", "arguments": '{"account":"savings"}', "output": '{"balance":500}'}]
        }])
        audit_assistants_run(openai, gdr, ctx, _make_run(), thread_id="th_1")
        payloads = _drain(gdr)
        event_types = [p.event_type for p in payloads]  # type: ignore[union-attr]
        assert "tool.invoked" in event_types
        assert "tool.completed" in event_types

    def test_function_call_without_output_emits_only_invoked(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        openai = _make_openai(steps=[{
            "tool_calls": [{"name": "transfer_money", "arguments": "{}", "output": None}]
        }])
        audit_assistants_run(openai, gdr, ctx, _make_run(), thread_id="th_1")
        payloads = _drain(gdr)
        event_types = [p.event_type for p in payloads]  # type: ignore[union-attr]
        assert event_types == ["tool.invoked"]

    def test_code_interpreter_step_emits_invoked_and_completed(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        openai = _make_openai(steps=[{
            "tool_calls": [{"type": "code_interpreter", "id": "ci_1"}]
        }])
        audit_assistants_run(openai, gdr, ctx, _make_run(), thread_id="th_1")
        payloads = _drain(gdr)
        event_types = [p.event_type for p in payloads]  # type: ignore[union-attr]
        assert event_types == ["tool.invoked", "tool.completed"]
        assert payloads[0].tool_name == "code_interpreter"  # type: ignore[union-attr]

    def test_failed_run_emits_tool_failed(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        run = MagicMock()
        run.id = "run_xyz"
        run.status = "failed"
        run.last_error = SimpleNamespace(code="rate_limit_exceeded", message="Too many requests")
        openai = _make_openai(steps=[])
        audit_assistants_run(openai, gdr, ctx, run, thread_id="th_1")
        payloads = _drain(gdr)
        assert len(payloads) == 1
        p = payloads[0]
        assert p.event_type == "tool.failed"  # type: ignore[union-attr]
        assert p.error_class == "rate_limit_exceeded"  # type: ignore[union-attr]

    def test_no_events_emitted_for_empty_successful_run(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        openai = _make_openai(steps=[])
        audit_assistants_run(openai, gdr, ctx, _make_run(), thread_id="th_1")
        assert _drain(gdr) == []

    def test_multiple_function_calls_in_one_step(
        self, client_and_ctx: tuple[GoderashClient, GoderashContext]
    ) -> None:
        gdr, ctx = client_and_ctx
        openai = _make_openai(steps=[{
            "tool_calls": [
                {"name": "fn_a", "arguments": "{}", "output": "ok"},
                {"name": "fn_b", "arguments": "{}", "output": "ok"},
            ]
        }])
        audit_assistants_run(openai, gdr, ctx, _make_run(), thread_id="th_1")
        payloads = _drain(gdr)
        assert len(payloads) == 4  # invoked + completed × 2
        names = {p.tool_name for p in payloads}  # type: ignore[union-attr]
        assert names == {"fn_a", "fn_b"}
