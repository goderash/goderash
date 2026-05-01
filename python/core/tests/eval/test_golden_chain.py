"""Eval: hash chain over the golden 7-event turn.

Locks down regression-prone behaviors:

1. `compute_hash` + `canonical_json` are deterministic across runs.
2. Re-canonicalizing a payload (re-ordering keys, re-encoding ints) does NOT
   change its hash. If these evals fail, the chain is no longer stable and
   every historical pack will refuse to validate.
3. Tampering and reordering are detected at the right index.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from goderash_core.ledger.chain import GENESIS_PREV_HASH, canonical_json, compute_hash, verify_chain

from .conftest import GoldenEvent


def test_golden_chain_verifies_clean(golden_chain_dicts: list[dict]) -> None:
    ok, broken = verify_chain(golden_chain_dicts)
    assert ok is True
    assert broken is None


def test_golden_chain_is_deterministic(golden_chain: Sequence[GoldenEvent]) -> None:
    """Two independent recomputations must yield bit-identical hashes."""
    prev = GENESIS_PREV_HASH
    for ev in golden_chain:
        recomputed = compute_hash(prev, ev.payload)
        assert recomputed == ev.hash, (
            f"non-deterministic hash at seq={ev.sequence_no}: "
            f"{recomputed} != {ev.hash}"
        )
        prev = ev.hash


def test_canonical_json_is_key_order_invariant() -> None:
    """Reshuffling input dict keys must not change the canonical form."""
    a = {"event_type": "tool.invoked", "tool_name": "x", "input_args_hash": "y"}
    b = {"input_args_hash": "y", "tool_name": "x", "event_type": "tool.invoked"}
    assert canonical_json(a) == canonical_json(b)
    assert compute_hash(GENESIS_PREV_HASH, a) == compute_hash(GENESIS_PREV_HASH, b)


def test_canonical_json_round_trips_through_json(
    golden_chain: Sequence[GoldenEvent],
) -> None:
    """Serializing → parsing → re-canonicalizing must not shift any hash."""
    for ev in golden_chain:
        round_tripped = json.loads(json.dumps(ev.payload))
        assert compute_hash(ev.prev_hash, round_tripped) == ev.hash


def test_tampering_breaks_at_first_mutated_event(
    golden_chain_dicts: list[dict],
) -> None:
    """Mutating any payload mid-chain must produce first_broken_index == idx."""
    tampered = [dict(e) for e in golden_chain_dicts]
    target = 3
    tampered[target] = {
        **tampered[target],
        "payload": {**tampered[target]["payload"], "tool_name": "evil_tool"},
    }
    ok, idx = verify_chain(tampered)
    assert ok is False
    assert idx == target


def test_reordering_breaks_chain(golden_chain_dicts: list[dict]) -> None:
    """Swapping two adjacent events must invalidate the chain at the swap point."""
    if len(golden_chain_dicts) < 3:
        pytest.skip("chain too short to reorder")
    swapped = [dict(e) for e in golden_chain_dicts]
    swapped[1], swapped[2] = swapped[2], swapped[1]
    ok, idx = verify_chain(swapped)
    assert ok is False
    assert idx is not None and idx >= 1
