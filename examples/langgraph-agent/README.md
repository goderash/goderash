# Example — LangGraph agent with Goderash audit

A tiny LangGraph ReAct agent with two tools (`check_balance`, `transfer_money`)
and a Goderash callback wired in. Every graph transition lands in the ledger as
a typed event.

## Prereqs

- Goderash core running (`make dev` from repo root)
- A seeded tenant + API key (`make seed`)
- Python 3.10+ with `uv` or `pip`

## Run

```bash
cd examples/langgraph-agent
uv sync   # or: pip install -e .

export GODERASH_API_KEY=<your-key>
export GODERASH_TENANT=<your-tenant>
export GODERASH_ENDPOINT=http://localhost:8000
export ANTHROPIC_API_KEY=<your-anthropic-key>   # or use a mock model

python agent.py "What's my balance?"
python agent.py "Transfer 100 USD from checking to savings"
```

## Check the ledger

```bash
curl -H "X-Goderash-Api-Key: $GODERASH_API_KEY" \
     -H "X-Goderash-Tenant: $GODERASH_TENANT" \
     "http://localhost:8000/v1/events?limit=20" | jq

curl -X POST \
     -H "X-Goderash-Api-Key: $GODERASH_API_KEY" \
     -H "X-Goderash-Tenant: $GODERASH_TENANT" \
     -H "Content-Type: application/json" \
     -d '{}' \
     http://localhost:8000/v1/verify
```

The verify endpoint walks the hash chain for your tenant and returns
`{ok: true, checked: N}` if the ledger is untampered.
