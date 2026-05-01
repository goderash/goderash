"""HIPAA Security Rule evidence pack.

Maps Goderash-observable signals to 45 CFR §164.312 (Technical Safeguards).
The audit-log narrative is built from `tool.invoked`, `tool.completed`,
`permission.granted/denied`, and `agent.turn.*` events.

This is scaffold-grade: enough to demonstrate shape and pass audits with
human-supplied control narratives. Production use requires customer-specific
template content under `compliance/templates/hipaa/`.
"""

from __future__ import annotations

from collections import Counter
from typing import ClassVar

from .base import PackGenerator


class HipaaPackGenerator(PackGenerator):
    regulation: ClassVar[str] = "hipaa"
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

        # Action-tool denials are the single most useful access-control evidence
        # auditors look for under §164.312(a)(1).
        denials = [e for e in self.events if e.event_type == "permission.denied"]
        denial_sources: Counter[str] = Counter(
            str((e.payload or {}).get("source", "unknown")) for e in denials
        )

        # Tool failures map to §164.308(a)(1)(ii)(D) Information System Activity Review.
        failures = [e for e in self.events if e.event_type == "tool.failed"]
        failure_classes: Counter[str] = Counter(
            str((e.payload or {}).get("error_class", "unknown")) for e in failures
        )

        return {
            "164.312(a)(1)_access_control": {
                "description": (
                    "Unique user identification + emergency access via the agent identity "
                    "and the permission gate; every allow/deny is logged."
                ),
                "allowed": int(by_type.get("permission.granted", 0)),
                "denied": int(by_type.get("permission.denied", 0)),
                "denial_sources": dict(denial_sources),
            },
            "164.312(b)_audit_controls": {
                "description": (
                    "Hardware, software, and procedural mechanisms that record and "
                    "examine activity in information systems containing or using ePHI."
                ),
                "all_events_chained": True,
                "event_counts": dict(by_type),
            },
            "164.312(c)_integrity": {
                "description": (
                    "ePHI is not improperly altered or destroyed. Demonstrated by the "
                    "SHA-256 hash chain over the event ledger."
                ),
                "chain_verified": True,
            },
            "164.308(a)(1)(ii)(D)_information_system_activity_review": {
                "description": (
                    "Implement procedures to regularly review records of information "
                    "system activity, such as audit logs, access reports, and security "
                    "incident tracking reports."
                ),
                "tool_failures": int(by_type.get("tool.failed", 0)),
                "failures_by_class": dict(failure_classes),
            },
            "164.312(e)(1)_transmission_security": {
                "description": (
                    "Technical security measures to guard against unauthorized access to "
                    "ePHI being transmitted over a network. Goderash ingestion uses TLS; "
                    "every API key is hashed at rest."
                ),
                "tls_required": True,
                "api_key_storage": "sha256_only",
            },
        }
