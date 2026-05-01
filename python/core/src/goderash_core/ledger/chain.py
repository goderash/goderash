"""SHA-256 hash chain.

Every event's hash = SHA-256( prev_hash || canonical_json(payload) ).
A chain verifier walks the ledger in order and confirms no row has been
mutated, removed, or reordered. The first event in a stream uses a
deterministic genesis sentinel as its `prev_hash`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

GENESIS_PREV_HASH = "0" * 64  # 32 zero bytes in hex


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8.

    Used for hashing — any variation in serialization would invalidate the chain.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def compute_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    """Compute the chained SHA-256 for a single event.

    The canonical form of `payload` — NOT the full envelope — is hashed.
    Hash-chain fields are excluded from the input by convention: the caller
    must pass the pre-hash payload.
    """
    h = hashlib.sha256()
    h.update(prev_hash.encode("ascii"))
    h.update(b"|")
    h.update(canonical_json(payload).encode("utf-8"))
    return h.hexdigest()


def verify_chain(events: Iterable[dict[str, Any]]) -> tuple[bool, int | None]:
    """Walk a sequence of event dicts and verify hash continuity.

    Returns `(ok, first_broken_index)`. On success, the index is None.

    Each event dict must contain `prev_hash`, `hash`, and a `payload` dict.
    """
    expected_prev = GENESIS_PREV_HASH
    for i, e in enumerate(events):
        prev_hash = e.get("prev_hash")
        actual_hash = e.get("hash")
        payload = e.get("payload")

        if prev_hash != expected_prev:
            return False, i
        if payload is None or actual_hash is None:
            return False, i

        recomputed = compute_hash(prev_hash, payload)
        if recomputed != actual_hash:
            return False, i

        expected_prev = actual_hash

    return True, None
