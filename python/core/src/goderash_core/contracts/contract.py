"""Contract schema.

Subset of Bitol v3.0.0 sufficient to express the invariants we observed in
data-contract-enforcer (week 7). Each contract has an id, a version, and a
list of clauses; each clause has a JSONPath-ish path, a check kind, and a
threshold or expected value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["info", "warn", "error", "critical"]
CheckKind = Literal[
    "type",
    "required",
    "in_range",
    "max",
    "min",
    "enum",
    "regex",
    "uuid",
    "datetime",
    "monotonic_increase",
    "non_null",
    "unique",
]


@dataclass(frozen=True)
class ContractClause:
    path: str
    check: CheckKind
    expected: Any = None
    severity: Severity = "error"
    description: str = ""


@dataclass(frozen=True)
class Contract:
    id: str
    version: str
    description: str = ""
    clauses: tuple[ContractClause, ...] = field(default_factory=tuple)

    def with_clauses(self, *clauses: ContractClause) -> "Contract":
        return Contract(
            id=self.id,
            version=self.version,
            description=self.description,
            clauses=self.clauses + tuple(clauses),
        )
