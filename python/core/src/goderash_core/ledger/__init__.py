"""Event-sourced ledger: append-only, hash-chained, upcast-aware."""

from .chain import canonical_json, compute_hash, verify_chain
from .store import EventLedger
from .upcast import UpcasterRegistry

__all__ = [
    "EventLedger",
    "UpcasterRegistry",
    "canonical_json",
    "compute_hash",
    "verify_chain",
]
