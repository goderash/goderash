"""Contract enforcer — type, range, enum, regex, uuid, monotonic checks."""

from __future__ import annotations

from goderash_core.contracts import Contract, ContractClause, ContractEnforcer


def test_required_field_missing_violates() -> None:
    c = Contract(id="t", version="1.0", clauses=(
        ContractClause(path="amount", check="required"),
    ))
    e = ContractEnforcer(c)
    v = e.evaluate({})
    assert len(v) == 1
    assert v[0].clause.path == "amount"


def test_in_range_passes_and_fails() -> None:
    c = Contract(id="t", version="1.0", clauses=(
        ContractClause(path="confidence", check="in_range", expected=(0.0, 1.0)),
    ))
    e = ContractEnforcer(c)
    assert e.evaluate({"confidence": 0.5}) == []
    assert len(e.evaluate({"confidence": 1.5})) == 1
    assert len(e.evaluate({"confidence": -0.1})) == 1


def test_max_amount_clause() -> None:
    c = Contract(id="t", version="1.0", clauses=(
        ContractClause(path="amount", check="max", expected=10_000, severity="critical"),
    ))
    e = ContractEnforcer(c)
    assert e.evaluate({"amount": 5_000}) == []
    v = e.evaluate({"amount": 50_000})
    assert v and v[0].severity == "critical"


def test_enum_check() -> None:
    c = Contract(id="t", version="1.0", clauses=(
        ContractClause(path="currency", check="enum", expected=["USD", "EUR"]),
    ))
    e = ContractEnforcer(c)
    assert e.evaluate({"currency": "USD"}) == []
    assert len(e.evaluate({"currency": "BTC"})) == 1


def test_regex_check() -> None:
    c = Contract(id="t", version="1.0", clauses=(
        ContractClause(path="account", check="regex", expected=r"^[0-9]{10}$"),
    ))
    e = ContractEnforcer(c)
    assert e.evaluate({"account": "1234567890"}) == []
    assert len(e.evaluate({"account": "abc"})) == 1


def test_uuid_check() -> None:
    c = Contract(id="t", version="1.0", clauses=(
        ContractClause(path="event_id", check="uuid"),
    ))
    e = ContractEnforcer(c)
    assert e.evaluate({"event_id": "00000000-0000-0000-0000-000000000000"}) == []
    assert len(e.evaluate({"event_id": "not-a-uuid"})) == 1


def test_nested_path_resolution() -> None:
    c = Contract(id="t", version="1.0", clauses=(
        ContractClause(path="$.payload.amount", check="max", expected=100),
    ))
    e = ContractEnforcer(c)
    assert e.evaluate({"payload": {"amount": 50}}) == []
    assert len(e.evaluate({"payload": {"amount": 500}})) == 1


def test_blame_chain_propagates() -> None:
    c = Contract(id="t", version="1.0", clauses=(
        ContractClause(path="amount", check="required"),
    ))
    e = ContractEnforcer(c)
    v = e.evaluate({}, blame_chain=("evt1", "evt2"))
    assert v[0].blame_chain == ("evt1", "evt2")
