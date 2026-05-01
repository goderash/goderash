"""Counterfactual projector — verifies decisions flip as expected under policy."""

from __future__ import annotations

from datetime import datetime, timezone

from goderash_core.whatif import WhatIfPolicy, WhatIfProjector


def _ev(seq: int, etype: str, tool: str = "transfer", **payload) -> dict:
    return {
        "sequence_no": seq,
        "event_type": etype,
        "occurred_at": datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc),
        "payload": {"event_type": etype, "tool_name": tool, **payload},
    }


def test_projector_denies_listed_tool() -> None:
    events = [_ev(1, "permission.granted", tool="transfer")]
    p = WhatIfProjector("t", WhatIfPolicy(deny_tools=("transfer",)))
    report = p.project(events)
    assert report.diffs[0].counter_decision == "deny"
    assert "deny_tools" in (report.diffs[0].reason or "")


def test_projector_velocity_count_cap() -> None:
    events = [
        _ev(i, "permission.granted", tool="transfer") for i in range(1, 6)
    ]
    p = WhatIfProjector("t", WhatIfPolicy(velocity_caps={"transfer": 2}))
    report = p.project(events)
    diffs = report.diffs
    # First 2 allowed, next 3 denied under counterfactual
    assert len(diffs) == 3
    assert all(d.counter_decision == "deny" for d in diffs)


def test_projector_no_change_when_within_cap() -> None:
    events = [_ev(1, "permission.granted"), _ev(2, "permission.granted")]
    p = WhatIfProjector("t", WhatIfPolicy(velocity_caps={"transfer": 5}))
    report = p.project(events)
    assert report.diffs == []


def test_projector_plan_mode_blocks_actions() -> None:
    events = [
        _ev(1, "permission.granted", tool="transfer", tool_category="action"),
        _ev(2, "permission.granted", tool="balance", tool_category="query"),
    ]
    p = WhatIfProjector("t", WhatIfPolicy(new_permission_mode="plan"))
    report = p.project(events)
    diffs = report.diffs
    assert len(diffs) == 1
    assert diffs[0].tool_name == "transfer"
    assert diffs[0].counter_decision == "deny"


def test_projector_summary_groups_by_tool() -> None:
    events = [
        _ev(1, "permission.granted", tool="transfer"),
        _ev(2, "permission.granted", tool="payout"),
    ]
    p = WhatIfProjector("t", WhatIfPolicy(deny_tools=("transfer", "payout")))
    summary = p.project(events).summary()
    assert summary["diffs"] == 2
    assert summary["would_deny_by_tool"] == {"transfer": 1, "payout": 1}
