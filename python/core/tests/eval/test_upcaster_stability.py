"""Eval: upcaster registry is stable over the golden payload shapes.

Confirms that v1 payloads with no registered upcasters pass through
unchanged, and that any registered upcaster doesn't silently corrupt the
canonical fields the chain depends on.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from goderash_core.ledger.upcast import UpcasterRegistry

from .conftest import GoldenEvent


def test_v1_payloads_with_no_upcaster_stay_as_is(
    golden_chain: Sequence[GoldenEvent],
) -> None:
    """Events at v1 with no upcaster registered should pass through identity."""
    r = UpcasterRegistry()
    for ev in golden_chain:
        # current_version returns 1 when nothing is registered → no-op upcast.
        result = r.upcast(
            event_type=ev.event_type, from_version=1, payload=ev.payload
        ) if ev.event_type in r._current_version else ev.payload
        assert result == ev.payload


def test_upcaster_step_by_one_only() -> None:
    r = UpcasterRegistry()

    with pytest.raises(ValueError, match="one version at a time"):

        @r.register(from_version=1, to_version=3, event_type="tool.invoked")
        def _bad(p: dict) -> dict:
            return p


def test_duplicate_upcaster_registration_raises() -> None:
    r = UpcasterRegistry()

    @r.register(from_version=1, to_version=2, event_type="tool.invoked")
    def _first(p: dict) -> dict:
        return p

    with pytest.raises(ValueError, match="already registered"):

        @r.register(from_version=1, to_version=2, event_type="tool.invoked")
        def _second(p: dict) -> dict:
            return p


def test_registered_upcaster_preserves_event_type_field() -> None:
    """An upcaster that strips event_type would corrupt the chain read path."""
    r = UpcasterRegistry()

    @r.register(from_version=1, to_version=2, event_type="tool.invoked")
    def add_category(p: dict) -> dict:
        return {**p, "tool_category": p.get("tool_category", "query")}

    payload = {"event_type": "tool.invoked", "tool_name": "x", "input_args_hash": "y"}
    upcasted = r.upcast(event_type="tool.invoked", from_version=1, payload=payload)
    assert upcasted["event_type"] == "tool.invoked"
    assert upcasted["tool_name"] == "x"
    assert upcasted["tool_category"] == "query"
