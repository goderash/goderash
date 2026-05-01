"""Run a contract against a value and surface violations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .contract import Contract, ContractClause, Severity


@dataclass(frozen=True)
class ContractViolation:
    contract_id: str
    contract_version: str
    clause: ContractClause
    severity: Severity
    observed: Any
    blame_chain: tuple[str, ...] = ()


class ContractEnforcer:
    """Stateless evaluator. Construct once, reuse across invocations."""

    def __init__(self, contract: Contract) -> None:
        self.contract = contract

    def evaluate(
        self,
        value: dict[str, Any],
        *,
        blame_chain: tuple[str, ...] = (),
    ) -> list[ContractViolation]:
        violations: list[ContractViolation] = []
        for clause in self.contract.clauses:
            actual = _resolve(value, clause.path)
            ok = _check(clause, actual)
            if not ok:
                violations.append(
                    ContractViolation(
                        contract_id=self.contract.id,
                        contract_version=self.contract.version,
                        clause=clause,
                        severity=clause.severity,
                        observed=actual,
                        blame_chain=blame_chain,
                    )
                )
        return violations


# ---- helpers --------------------------------------------------------------


_MISSING = object()


def _resolve(value: dict[str, Any], path: str) -> Any:
    if path in ("", "$"):
        return value
    parts = path.lstrip("$").lstrip(".").split(".")
    current: Any = value
    for p in parts:
        if not p:
            continue
        if isinstance(current, dict):
            current = current.get(p, _MISSING)
        else:
            return _MISSING
    return current


def _check(clause: ContractClause, actual: Any) -> bool:
    kind = clause.check

    if kind == "required":
        return actual is not _MISSING and actual is not None
    if actual is _MISSING:
        # All other checks treat missing as failed unless `required` is False.
        return False

    if kind == "non_null":
        return actual is not None
    if kind == "type":
        expected = clause.expected
        if expected == "int":
            return isinstance(actual, int) and not isinstance(actual, bool)
        if expected == "float":
            return isinstance(actual, (int, float)) and not isinstance(actual, bool)
        if expected == "str":
            return isinstance(actual, str)
        if expected == "bool":
            return isinstance(actual, bool)
        if expected == "list":
            return isinstance(actual, list)
        if expected == "dict":
            return isinstance(actual, dict)
        return type(actual).__name__ == str(expected)
    if kind == "in_range":
        if not isinstance(actual, (int, float)):
            return False
        lo, hi = clause.expected
        return lo <= actual <= hi
    if kind == "max":
        return isinstance(actual, (int, float)) and actual <= clause.expected
    if kind == "min":
        return isinstance(actual, (int, float)) and actual >= clause.expected
    if kind == "enum":
        return actual in (clause.expected or [])
    if kind == "regex":
        if not isinstance(actual, str):
            return False
        return re.search(str(clause.expected), actual) is not None
    if kind == "uuid":
        if not isinstance(actual, str):
            return False
        return re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            actual,
        ) is not None
    if kind == "datetime":
        if isinstance(actual, datetime):
            return True
        if isinstance(actual, str):
            try:
                datetime.fromisoformat(actual.replace("Z", "+00:00"))
                return True
            except ValueError:
                return False
        return False
    if kind == "monotonic_increase":
        # Expects clause.expected to be the prior value
        try:
            return float(actual) > float(clause.expected)
        except (TypeError, ValueError):
            return False
    if kind == "unique":
        if not isinstance(actual, list):
            return False
        return len(set(map(repr, actual))) == len(actual)

    return False
