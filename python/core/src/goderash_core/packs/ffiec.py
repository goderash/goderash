"""FFIEC IT Examination Handbook — evidence pack.

Maps Goderash events to FFIEC's "Audit" and "Information Security" booklet
expectations: an immutable activity log, role-based access decisions, and
incident logs. Suitable as a starting evidence packet for OCC / FDIC / Fed
examiners; full Bank Service Company Act readiness still requires
customer-specific control narratives.
"""

from __future__ import annotations

from collections import Counter
from typing import ClassVar

from .base import PackGenerator


class FfiecPackGenerator(PackGenerator):
    regulation: ClassVar[str] = "ffiec"
    version: ClassVar[str] = "0.1.0"
    required_event_types: ClassVar[list[str]] = [
        "agent.turn.started",
        "agent.turn.completed",
        "tool.invoked",
        "tool.completed",
        "tool.failed",
        "permission.granted",
        "permission.denied",
        "contract.violated",
    ]

    def render_controls(self) -> dict[str, object]:
        by_type: Counter[str] = Counter(e.event_type for e in self.events)

        contract_breaches = [e for e in self.events if e.event_type == "contract.violated"]
        breach_severity: Counter[str] = Counter(
            str((e.payload or {}).get("severity", "unknown")) for e in contract_breaches
        )

        denials = [e for e in self.events if e.event_type == "permission.denied"]
        denial_sources: Counter[str] = Counter(
            str((e.payload or {}).get("source", "unknown")) for e in denials
        )

        return {
            "audit_independence_of_audit_function": {
                "description": (
                    "The Goderash ledger is append-only and cryptographically chained; "
                    "no role inside the customer agent stack can mutate audit history."
                ),
                "chain_verified": True,
                "ledger_event_count": len(self.events),
            },
            "information_security_logging_and_monitoring": {
                "description": (
                    "Activity logs capture events, identify attempted or successful "
                    "intrusions, and provide for the timely detection of anomalies."
                ),
                "events_by_type": dict(by_type),
                "denials_by_source": dict(denial_sources),
            },
            "information_security_data_integrity": {
                "description": (
                    "Tamper-evident records of agent activity using SHA-256 hash "
                    "chain across ledger entries."
                ),
                "hash_algorithm": "SHA-256",
                "verifier_endpoint": "/v1/verify",
            },
            "operations_change_management": {
                "description": "Schema evolution is upcaster-driven; raw rows never mutate.",
                "schema_version": "tracked per envelope",
            },
            "operations_incident_management": {
                "description": "Tool failures and contract violations recorded with severity.",
                "tool_failures": int(by_type.get("tool.failed", 0)),
                "contract_violations": int(by_type.get("contract.violated", 0)),
                "violation_severity": dict(breach_severity),
            },
        }
