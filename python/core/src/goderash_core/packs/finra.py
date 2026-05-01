"""FINRA Rule 4511 / 17a-4 record-retention evidence pack.

Provides the immutable, time-stamped record of agent activity that broker-
dealers are required to retain. Combined with WORM storage at the
infrastructure layer, this is enough to demonstrate compliance with
SEC Rule 17a-4 books-and-records requirements for AI-mediated activity.
"""

from __future__ import annotations

from collections import Counter
from typing import ClassVar

from .base import PackGenerator


class FinraPackGenerator(PackGenerator):
    regulation: ClassVar[str] = "finra"
    version: ClassVar[str] = "0.1.0"
    required_event_types: ClassVar[list[str]] = [
        "agent.turn.started",
        "agent.turn.completed",
        "tool.invoked",
        "tool.completed",
        "tool.failed",
        "permission.granted",
        "permission.denied",
    ]

    def render_controls(self) -> dict[str, object]:
        by_type: Counter[str] = Counter(e.event_type for e in self.events)
        return {
            "rule_4511_general_books_and_records": {
                "description": (
                    "Member firms must make and preserve books and records as "
                    "described by SEA Rules 17a-3 and 17a-4."
                ),
                "ledger_entries": len(self.events),
                "events_by_type": dict(by_type),
            },
            "rule_3110_supervision": {
                "description": (
                    "Supervisory framework is reflected in permission-mode events: "
                    "every action attempted by the agent has a recorded decision."
                ),
                "actions_allowed": int(by_type.get("permission.granted", 0)),
                "actions_denied": int(by_type.get("permission.denied", 0)),
            },
            "sea_17a4_retention": {
                "description": (
                    "Records preserved in non-rewritable, non-erasable format. "
                    "Goderash emits to an append-only ledger with hash chain; pair "
                    "with WORM-compliant storage at the infra tier."
                ),
                "hash_algorithm": "SHA-256",
                "appendOnly": True,
            },
        }


class Sec17a4PackGenerator(PackGenerator):
    """SEC Rule 17a-4 books-and-records evidence — overlaps with FINRA."""

    regulation: ClassVar[str] = "sec_17a4"
    version: ClassVar[str] = "0.1.0"
    required_event_types: ClassVar[list[str]] = FinraPackGenerator.required_event_types

    def render_controls(self) -> dict[str, object]:
        # Reuse FINRA control rendering — 17a-4 is the underlying SEA rule.
        finra = FinraPackGenerator(
            session=self.session,
            tenant_id=self.tenant_id,
            start=self.start,
            end=self.end,
        )
        finra.events = self.events
        finra.chain_ok = self.chain_ok
        return finra.render_controls()
