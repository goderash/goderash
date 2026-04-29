# Quickstart (15 minutes)

## 1. Start the control plane

```bash
git clone <repo> goderash && cd goderash
cp .env.example .env
make setup
make dev
```

Postgres, Redis, and the FastAPI core come up on `http://localhost:8000`.

- `GET /health` → liveness
- `GET /ready` → DB reachable
- `GET /docs` → interactive OpenAPI

## 2. Create a tenant + API key

```bash
make seed
# or, manually:
curl -X POST http://localhost:8000/v1/admin/tenants \
  -H "X-Goderash-Api-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"id":"demo","display_name":"Demo Co"}'

curl -X POST http://localhost:8000/v1/admin/keys \
  -H "X-Goderash-Api-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"demo","label":"local-dev"}'
# -> returns {"api_key":"gdr_...","id":"...","tenant_id":"demo",...}
# Save this key — it's shown only once.
```

## 3. Wrap your agent (Python)

```python
from goderash_sdk import GoderashClient, wrap_tool

goderash = GoderashClient(
    api_key="gdr_...",
    tenant="demo",
    agent_id="ops-agent-v1",
    endpoint="http://localhost:8000",
)

@wrap_tool(goderash, category="action", confirmation="biometric")
def transfer_money(src: str, dst: str, amount: float) -> dict:
    return {"status": "queued"}

with goderash.turn() as ctx:
    transfer_money("checking", "savings", 100.0, _goderash_context=ctx)
```

## 4. Wrap your agent (TypeScript)

```ts
import { GoderashClient, wrapTool } from '@goderash/sdk'

const goderash = new GoderashClient({
  apiKey: process.env.GODERASH_API_KEY!,
  tenant: 'demo',
  agentId: 'ops-agent-v1',
  endpoint: 'http://localhost:8000',
})

const ctx = goderash.newContext()

const transfer = wrapTool(
  goderash,
  { category: 'action', confirmation: 'biometric', context: ctx },
  async (src: string, dst: string, amount: number) => ({ status: 'queued' }),
)

await transfer('checking', 'savings', 100)
await goderash.flush()
```

## 5. Verify the chain

```bash
curl -X POST http://localhost:8000/v1/verify \
  -H "X-Goderash-Api-Key: $GODERASH_API_KEY" \
  -H "X-Goderash-Tenant: demo" \
  -H "Content-Type: application/json" \
  -d '{}'
# -> {"ok": true, "checked": 4, "first_broken_index": null}
```

## 6. Browse events

```bash
curl "http://localhost:8000/v1/events?limit=20" \
  -H "X-Goderash-Api-Key: $GODERASH_API_KEY" \
  -H "X-Goderash-Tenant: demo" | jq
```

## Next

- See [examples/langgraph-agent/](../examples/langgraph-agent/) for a full ReAct agent with a Goderash callback.
- See [architecture.md](architecture.md) for the ledger internals.
- See [CLAUDE.md](../CLAUDE.md) for contributor conventions.
