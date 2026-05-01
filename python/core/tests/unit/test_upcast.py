"""Upcaster registry behavior."""

from __future__ import annotations

import pytest

from goderash_core.ledger.upcast import UpcasterRegistry


def test_upcaster_missing_path_raises() -> None:
    reg = UpcasterRegistry()
    with pytest.raises(LookupError):
        reg.upcast(event_type="tool.invoked", from_version=1, payload={})


def test_upcaster_runs_chain() -> None:
    reg = UpcasterRegistry()

    @reg.register(from_version=1, to_version=2, event_type="tool.invoked")
    def _v1_to_v2(p: dict) -> dict:
        p["category"] = "query"
        return p

    @reg.register(from_version=2, to_version=3, event_type="tool.invoked")
    def _v2_to_v3(p: dict) -> dict:
        p["category_v2"] = p.pop("category")
        return p

    out = reg.upcast(event_type="tool.invoked", from_version=1, payload={"tool": "x"})
    assert out == {"tool": "x", "category_v2": "query"}
    assert reg.current_version("tool.invoked") == 3


def test_upcaster_rejects_non_sequential() -> None:
    reg = UpcasterRegistry()
    with pytest.raises(ValueError):
        reg.register(from_version=1, to_version=3, event_type="anything")(lambda p: p)
