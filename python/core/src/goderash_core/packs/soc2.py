"""SOC 2 evidence-pack generator (scaffold).

This is an intentionally small first pass — enough to demonstrate the shape
and run end-to-end, not enough to hand to an auditor. The real content lives
under `compliance/templates/soc2/` and is expanded per-customer during FDE
onboarding.
"""

from __future__ import annotations

from collections import Counter
from typing import ClassVar

from .base import PackGenerator


class Soc2PackGenerator(PackGenerator):
    regulation: ClassVar[str] = "soc2"
    version: ClassVar[str] = "0.1.0"
    required_event_types: ClassVar[list[str]] = [
        "tool.invoked",
        "tool.completed",
        "tool.failed",
        "permission.granted",
        "permission.denied",
        "agent.turn.started",
        "agent.turn.completed",
    ]

    def render_controls(self) -> dict[str, object]:
        by_type: Counter[str] = Counter(e.event_type for e in self.events)

        denials = [e for e in self.events if e.event_type == "permission.denied"]
        denial_reasons: Counter[str] = Counter(
            str((e.payload or {}).get("reason", "unknown")) for e in denials
        )

        failed_tools = [e for e in self.events if e.event_type == "tool.failed"]
        failure_by_tool: Counter[str] = Counter(
            str((e.payload or {}).get("tool_name", "unknown")) for e in failed_tools
        )

        # Minimal mapping — expanded per Trust Services Criteria during FDE.
        return {
            "CC6.1_logical_access": {
                "description": (
                    "Every action attempted is recorded. Allowed vs denied "
                    "decisions are timestamped, attributed, and hash-chained."
                ),
                "allowed_actions": int(by_type.get("permission.granted", 0)),
                "denied_actions": int(by_type.get("permission.denied", 0)),
                "denial_reasons": dict(denial_reasons),
            },
            "CC7.2_monitoring": {
                "description": "All agent activity is captured in the ledger with a SHA-256 chain.",
                "event_counts": dict(by_type),
            },
            "CC7.4_incidents": {
                "description": "Tool failures are captured per-tool for incident review.",
                "failures_by_tool": dict(failure_by_tool),
            },
        }
