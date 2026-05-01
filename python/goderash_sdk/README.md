# goderash-sdk

**Python SDK for Goderash — audit any AI agent with one import.**

```bash
pip install goderash-sdk
```

## Quick start

```python
from goderash_sdk import GoderashClient, wrap_tool

goderash = GoderashClient(
    api_key="gdr_...",
    tenant="acme-finance",
    agent_id="portfolio-advisor-v1",
)

@wrap_tool(goderash, category="action", confirmation="biometric")
def transfer_money(src: str, dst: str, amount: float) -> dict:
    return {"status": "queued"}

with goderash.turn() as ctx:
    transfer_money("checking", "savings", 100.0, _goderash_context=ctx)
# Every call is appended to the hash-chained audit ledger automatically.
```

## Runtime guards

```python
from goderash_sdk.guards import (
    GuardChain, FraudGuard, VelocityLimiter, VelocityRule, ConversationBudget,
)

guards = GuardChain(
    FraudGuard(),
    VelocityLimiter(rules_by_tool={
        "transfer_money": [
            VelocityRule(window_seconds=3600, max_count=5, label="5/hour"),
        ],
    }),
    ConversationBudget(max_tool_calls=20, max_tokens=200_000),
)

decision = guards.evaluate(goderash, ctx, tool_name="transfer_money", amount=500)
if decision.allow:
    transfer_money(...)
```

## Links

- [GitHub](https://github.com/goderash/goderash)
- [Website](https://goderash.com)
- [Full docs](https://github.com/goderash/goderash/tree/main/docs)
