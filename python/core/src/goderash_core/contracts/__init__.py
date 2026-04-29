"""Data-contract enforcement.

A contract is a typed schema + invariants for a tool's input/output. Goderash
enforces contracts at the SDK boundary: every wrapped call validates input
and output against the contract, and any violation emits a typed
`contract.violated` event into the ledger with a `blame_chain`.
"""

from .contract import Contract, ContractClause, Severity
from .enforcer import ContractEnforcer, ContractViolation

__all__ = [
    "Contract",
    "ContractClause",
    "ContractEnforcer",
    "ContractViolation",
    "Severity",
]
