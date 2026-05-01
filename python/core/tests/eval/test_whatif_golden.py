"""Eval: What-If projector over the golden turn.

Pins the semantic contracts that regulators rely on:
- Empty policy → zero diffs (clean turn stays clean).
- deny_tools blocks a known tool → exactly one diff.
- plan mode blocks action-category tools → one diff, query untouched.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

import pytest

from goderash_core.whatif import WhatIfPolicy, WhatIfProjector

from .conftest import GOLDEN_TENANT, GoldenEvent


def _permission_events(golden_chain: Sequence[GoldenEvent]) -> list[dict]:
    return [
        {
            "sequence_no": e.sequence_no,
            "event_type": e.event_type,
            "occurred_at": e.occurred_at,
            "payload": e.payload,
        }
        for e in golden_chain
        if e.event_type in ("permission.granted", "permission.denied")
    ]


def test_empty_policy_produces_zero_diffs(golden_chain: Sequence[GoldenEvent]) -> None:
    events = _permission_events(golden_chain)
    projector = WhatIfProjector(GOLDEN_TENANT, WhatIfPolicy())
    report = projector.project(events)
    assert report.diffs == []
    assert report.summary()["diffs"] == 0


def test_deny_tools_flips_granted_to_denied(golden_chain: Sequence[GoldenEvent]) -> None:
    events = _permission_events(golden_chain)
    projector = WhatIfProjector(
        GOLDEN_TENANT, WhatIfPolicy(deny_tools=("transfer_money",))
    )
    report = projector.project(events)
    assert len(report.diffs) == 1
    assert report.diffs[0].tool_name == "transfer_money"
    assert report.diffs[0].counter_decision == "deny"


def test_plan_mode_blocks_actions_not_queries(golden_chain: Sequence[GoldenEvent]) -> None:
    events = _permission_events(golden_chain)
    projector = WhatIfProjector(GOLDEN_TENANT, WhatIfPolicy(new_permission_mode="plan"))
    report = projector.project(events)
    # Golden turn has one action-category grant (transfer_money) → 1 diff.
    assert len(report.diffs) == 1
    assert report.diffs[0].counter_decision == "deny"


def test_summary_groups_by_tool(golden_chain: Sequence[GoldenEvent]) -> None:
    events = _permission_events(golden_chain)
    projector = WhatIfProjector(
        GOLDEN_TENANT, WhatIfPolicy(deny_tools=("transfer_money",))
    )
    summary = projector.project(events).summary()
    assert summary["would_deny_by_tool"]["transfer_money"] == 1
