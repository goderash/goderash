"""Eval: SOC 2 controls renderer over the golden turn.

Pins the *shape* of the controls dictionary the SOC 2 pack emits — what
auditor reviewers would actually open. If a control ID changes silently,
this eval fails before it reaches a customer ZIP.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from goderash_core.packs.soc2 import Soc2PackGenerator

from .conftest import GoldenEvent


def _as_event_row(ev: GoldenEvent) -> SimpleNamespace:
    """SOC 2 renderer only reads `.event_type` and `.payload` — duck-type it."""
    return SimpleNamespace(event_type=ev.event_type, payload=ev.payload)


def _make_generator(events: Sequence[GoldenEvent]) -> Soc2PackGenerator:
    now = datetime.now(timezone.utc)
    gen = Soc2PackGenerator(
        session=None,  # type: ignore[arg-type] — render_controls doesn't touch the session
        tenant_id="demo",
        start=now - timedelta(hours=1),
        end=now,
    )
    gen.events = [_as_event_row(e) for e in events]  # type: ignore[assignment]
    return gen


def test_soc2_control_ids_are_stable(golden_chain: Sequence[GoldenEvent]) -> None:
    controls = _make_generator(golden_chain).render_controls()
    assert set(controls.keys()) == {
        "CC6.1_logical_access",
        "CC7.2_monitoring",
        "CC7.4_incidents",
    }


def test_soc2_logical_access_counts_are_correct(
    golden_chain: Sequence[GoldenEvent],
) -> None:
    controls = _make_generator(golden_chain).render_controls()
    cc61 = controls["CC6.1_logical_access"]
    # Golden turn has exactly one permission.granted, no permission.denied.
    assert cc61["allowed_actions"] == 1
    assert cc61["denied_actions"] == 0
    assert cc61["denial_reasons"] == {}


def test_soc2_monitoring_event_counts_match_golden(
    golden_chain: Sequence[GoldenEvent],
) -> None:
    controls = _make_generator(golden_chain).render_controls()
    counts = controls["CC7.2_monitoring"]["event_counts"]
    expected = {
        "agent.turn.started": 1,
        "agent.turn.completed": 1,
        "llm.call.started": 1,
        "llm.call.completed": 1,
        "tool.invoked": 1,
        "tool.completed": 1,
        "permission.granted": 1,
    }
    assert counts == expected


def test_soc2_incidents_empty_on_clean_turn(
    golden_chain: Sequence[GoldenEvent],
) -> None:
    controls = _make_generator(golden_chain).render_controls()
    assert controls["CC7.4_incidents"]["failures_by_tool"] == {}


def test_soc2_incidents_aggregate_failures_by_tool(
    golden_chain: Sequence[GoldenEvent],
) -> None:
    """Inject two failures and verify the aggregator groups them per-tool."""
    extra = [
        GoldenEvent(
            sequence_no=8,
            event_type="tool.failed",
            payload={"event_type": "tool.failed", "tool_name": "transfer_money",
                     "error_class": "Timeout", "error_message": "x", "duration_ms": 5},
            occurred_at=golden_chain[0].occurred_at,
            prev_hash="0" * 64,
            hash="f" * 64,
        ),
        GoldenEvent(
            sequence_no=9,
            event_type="tool.failed",
            payload={"event_type": "tool.failed", "tool_name": "transfer_money",
                     "error_class": "Timeout", "error_message": "x", "duration_ms": 5},
            occurred_at=golden_chain[0].occurred_at,
            prev_hash="0" * 64,
            hash="f" * 64,
        ),
    ]
    controls = _make_generator(list(golden_chain) + extra).render_controls()
    assert controls["CC7.4_incidents"]["failures_by_tool"] == {"transfer_money": 2}
