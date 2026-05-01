"""Exercise `wrap_tool` against a mocked transport."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from goderash_sdk import GoderashClient, wrap_tool


@pytest.fixture
def client() -> GoderashClient:
    return GoderashClient(
        api_key="gdr_test_abc",
        tenant="test-tenant",
        agent_id="unit-agent",
        endpoint="http://fake",
        batch_size=1000,
    )


def test_wrap_tool_emits_invoked_and_completed(client: GoderashClient) -> None:
    @wrap_tool(client, category="query")
    def check_balance(user_id: str) -> dict[str, Any]:
        return {"balance": 100}

    ctx = client.new_context()
    with patch.object(client, "flush_sync"):
        result = check_balance("u1", _goderash_context=ctx)

    assert result == {"balance": 100}
    types = [e.payload.event_type for e in client._state.buffer]
    assert types == ["tool.invoked", "tool.completed"]


def test_wrap_tool_emits_failed_on_exception(client: GoderashClient) -> None:
    @wrap_tool(client, category="action", confirmation="biometric")
    def transfer(amount: int) -> None:
        raise RuntimeError("network down")

    ctx = client.new_context()
    with patch.object(client, "flush_sync"), pytest.raises(RuntimeError):
        transfer(50, _goderash_context=ctx)

    types = [e.payload.event_type for e in client._state.buffer]
    assert types == ["tool.invoked", "tool.failed"]


def test_wrap_tool_noop_without_context(client: GoderashClient) -> None:
    @wrap_tool(client, category="query")
    def ping() -> str:
        return "pong"

    # Without a context, the wrapper passes through without emitting.
    assert ping() == "pong"
    assert client._state.buffer == []
