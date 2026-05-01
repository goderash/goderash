"""Counterfactual replay engine.

Replays a tenant's history under an alternate `WhatIfPolicy` and produces:

- the counterfactual stream of decisions ("what would have happened"),
- a delta vs. the real ledger (which `permission.granted` would have flipped
  to `permission.denied`, which tools would have been blocked outright,
  which actions would have escalated confirmation type).

The projector is **read-only**: it never mutates the source ledger. The
output stream lives in memory; persisting counterfactual ledgers into a
scratch schema is left to a higher-level orchestrator.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class WhatIfPolicy:
    """An alternate policy bundle.

    All fields default to "no override". Combine policies by merging fields
    from many bundles into one before passing to the projector.
    """

    velocity_caps: dict[str, int] = field(default_factory=dict)
    """Map `tool_name -> per-day count cap`. None for no cap."""

    velocity_amount_caps: dict[str, float] = field(default_factory=dict)
    """Map `tool_name -> per-day cumulative `amount` cap`."""

    deny_tools: tuple[str, ...] = ()
    """Tools that would have been entirely denied."""

    require_confirmation: tuple[str, ...] = ()
    """Tools that would have been forced into a stricter confirmation type."""

    new_permission_mode: Literal["plan", "default", "auto", "strict"] | None = None


Verdict = Literal["allow", "deny", "escalate"]


@dataclass(frozen=True)
class CounterfactualEvent:
    sequence_no: int
    event_type: str
    tool_name: str | None
    real_decision: Verdict
    counter_decision: Verdict
    reason: str | None = None
    diff: bool = False  # True if real != counter


@dataclass
class WhatIfReport:
    tenant_id: str
    policy: WhatIfPolicy
    total_real_events: int
    counter_events: list[CounterfactualEvent]

    @property
    def diffs(self) -> list[CounterfactualEvent]:
        return [c for c in self.counter_events if c.diff]

    def summary(self) -> dict[str, Any]:
        diffs = self.diffs
        denied_actions: dict[str, int] = defaultdict(int)
        escalated: dict[str, int] = defaultdict(int)
        for d in diffs:
            if d.counter_decision == "deny" and d.tool_name:
                denied_actions[d.tool_name] += 1
            if d.counter_decision == "escalate" and d.tool_name:
                escalated[d.tool_name] += 1
        return {
            "tenant_id": self.tenant_id,
            "total_real_events": self.total_real_events,
            "diffs": len(diffs),
            "would_deny_by_tool": dict(denied_actions),
            "would_escalate_by_tool": dict(escalated),
        }


@dataclass
class WhatIfProjector:
    tenant_id: str
    policy: WhatIfPolicy

    # Per-day counters keyed by (tool_name, YYYY-MM-DD)
    _count_seen: dict[tuple[str, str], int] = field(default_factory=dict)
    _amount_seen: dict[tuple[str, str], float] = field(default_factory=dict)

    def project(self, events: list[dict[str, Any]]) -> WhatIfReport:
        """Walk events in chain order; produce a counterfactual decision for
        each tool-related event and accumulate the diff.
        """
        out: list[CounterfactualEvent] = []

        for e in events:
            payload = e.get("payload") or {}
            event_type = payload.get("event_type") or e.get("event_type")
            seq = int(e.get("sequence_no") or 0)

            if event_type not in {
                "tool.invoked",
                "permission.granted",
                "permission.denied",
            }:
                continue

            tool_name = str(payload.get("tool_name") or "")
            real_decision: Verdict = (
                "deny" if event_type == "permission.denied" else "allow"
            )

            counter_decision, reason = self._decide(payload, tool_name, e.get("occurred_at"))
            out.append(
                CounterfactualEvent(
                    sequence_no=seq,
                    event_type=str(event_type),
                    tool_name=tool_name or None,
                    real_decision=real_decision,
                    counter_decision=counter_decision,
                    reason=reason,
                    diff=(real_decision != counter_decision),
                )
            )

        return WhatIfReport(
            tenant_id=self.tenant_id,
            policy=self.policy,
            total_real_events=len(events),
            counter_events=out,
        )

    # ---- decision helpers --------------------------------------------

    def _decide(
        self,
        payload: dict[str, Any],
        tool_name: str,
        occurred_at: Any,
    ) -> tuple[Verdict, str | None]:
        if tool_name in self.policy.deny_tools:
            return "deny", "policy:deny_tools"

        if self.policy.new_permission_mode == "plan":
            category = str(payload.get("tool_category") or "query")
            if category == "action":
                return "deny", "policy:plan_mode_action_blocked"

        # Velocity caps (per day)
        day = _day_key(occurred_at)
        if tool_name and self.policy.velocity_caps:
            cap = self.policy.velocity_caps.get(tool_name)
            if cap is not None:
                key = (tool_name, day)
                self._count_seen[key] = self._count_seen.get(key, 0) + 1
                if self._count_seen[key] > cap:
                    return "deny", f"policy:velocity_count {tool_name}={self._count_seen[key]}/{cap}"

        if tool_name and self.policy.velocity_amount_caps:
            amount_cap = self.policy.velocity_amount_caps.get(tool_name)
            if amount_cap is not None:
                attempted = float(
                    (payload.get("input_args_preview") or {}).get("amount") or 0.0
                )
                key = (tool_name, day)
                projected = self._amount_seen.get(key, 0.0) + attempted
                self._amount_seen[key] = projected
                if projected > amount_cap:
                    return "deny", f"policy:velocity_amount {tool_name}={projected:.2f}/{amount_cap:.2f}"

        if tool_name in self.policy.require_confirmation:
            return "escalate", "policy:require_confirmation"

        return "allow", None


def _day_key(occurred_at: Any) -> str:
    if occurred_at is None:
        return "1970-01-01"
    try:
        if hasattr(occurred_at, "date"):
            return occurred_at.date().isoformat()
        return str(occurred_at)[:10]
    except Exception:
        return "1970-01-01"
