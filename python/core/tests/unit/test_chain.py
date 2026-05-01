"""Hash-chain correctness and tampering detection."""

from __future__ import annotations

from goderash_core.ledger.chain import (
    GENESIS_PREV_HASH,
    canonical_json,
    compute_hash,
    verify_chain,
)


def _build_chain(n: int) -> list[dict]:
    events: list[dict] = []
    prev = GENESIS_PREV_HASH
    for i in range(n):
        payload = {"i": i, "msg": f"hello {i}"}
        h = compute_hash(prev, payload)
        events.append({"prev_hash": prev, "hash": h, "payload": payload})
        prev = h
    return events


def test_canonical_json_is_deterministic() -> None:
    a = canonical_json({"b": 1, "a": 2})
    b = canonical_json({"a": 2, "b": 1})
    assert a == b
    assert a == '{"a":2,"b":1}'


def test_chain_of_one_is_valid() -> None:
    chain = _build_chain(1)
    ok, broken = verify_chain(chain)
    assert ok and broken is None


def test_chain_of_many_is_valid() -> None:
    chain = _build_chain(50)
    ok, broken = verify_chain(chain)
    assert ok and broken is None


def test_tampered_payload_is_detected() -> None:
    chain = _build_chain(10)
    chain[5]["payload"]["msg"] = "MUTATED"
    ok, broken = verify_chain(chain)
    assert ok is False
    assert broken == 5


def test_tampered_hash_is_detected() -> None:
    chain = _build_chain(10)
    chain[3]["hash"] = "0" * 64
    ok, broken = verify_chain(chain)
    assert ok is False
    assert broken == 3


def test_reordered_events_are_detected() -> None:
    chain = _build_chain(10)
    chain[2], chain[3] = chain[3], chain[2]
    ok, broken = verify_chain(chain)
    assert ok is False
    assert broken == 2


def test_missing_event_is_detected() -> None:
    chain = _build_chain(10)
    chain.pop(5)
    ok, broken = verify_chain(chain)
    assert ok is False
    assert broken == 5
