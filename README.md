# Goderash

> **Audit & governance fabric for regulated AI agents.** Tamper-evident, hash-chained, regulator-ready.

[![license](https://img.shields.io/github/license/goderash/goderash.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![npm](https://img.shields.io/npm/v/@goderash/sdk.svg?label=%40goderash%2Fsdk)](https://www.npmjs.com/package/@goderash/sdk)
[![pypi](https://img.shields.io/pypi/v/goderash-sdk.svg?label=goderash-sdk)](https://pypi.org/project/goderash-sdk/)

📦 **GitHub:** [goderash/goderash](https://github.com/goderash/goderash)

Wrap any agent framework (LangGraph, OpenAI Assistants, Anthropic Messages, LangChain, AutoGen) with one SDK and get:

- **Event-sourced audit ledger** — append-only, SHA-256 hash-chained, tamper-evident, multi-tenant.
- **Upcasting registry** — evolve event schemas without rewriting history.
- **Data-contract enforcement** — type / range / regex / monotonic checks with blame-chain attribution.
- **What-If projector** — replay history under alternate velocity caps, deny lists, or permission modes; deterministic counterfactual diffs.
- **Compliance packs** — one-click signed evidence ZIPs for SOC 2, HIPAA, FFIEC, FINRA, SEC Rule 17a-4.
- **Runtime safety stack** — fraud guard, velocity limits, permission modes, conversation budgets, cancellation tokens (battle-tested in a banking-grade AI agent in production).

## Packages

### TypeScript (npm)

| Package | Version | Weekly Downloads | Description |
|---|---|---|---|
| [`@goderash/sdk`](https://www.npmjs.com/package/@goderash/sdk) | [![npm](https://img.shields.io/npm/v/@goderash/sdk.svg)](https://www.npmjs.com/package/@goderash/sdk) | [![dl](https://img.shields.io/npm/dw/@goderash/sdk.svg)](https://www.npmjs.com/package/@goderash/sdk) | Core SDK + runtime guards |
| [`@goderash/adapter-claude-sdk`](https://www.npmjs.com/package/@goderash/adapter-claude-sdk) | [![npm](https://img.shields.io/npm/v/@goderash/adapter-claude-sdk.svg)](https://www.npmjs.com/package/@goderash/adapter-claude-sdk) | [![dl](https://img.shields.io/npm/dw/@goderash/adapter-claude-sdk.svg)](https://www.npmjs.com/package/@goderash/adapter-claude-sdk) | Anthropic Messages / Claude SDK |
| [`@goderash/adapter-openai-assistants`](https://www.npmjs.com/package/@goderash/adapter-openai-assistants) | [![npm](https://img.shields.io/npm/v/@goderash/adapter-openai-assistants.svg)](https://www.npmjs.com/package/@goderash/adapter-openai-assistants) | [![dl](https://img.shields.io/npm/dw/@goderash/adapter-openai-assistants.svg)](https://www.npmjs.com/package/@goderash/adapter-openai-assistants) | OpenAI Assistants API |
| [`@goderash/adapter-langgraph`](https://www.npmjs.com/package/@goderash/adapter-langgraph) | [![npm](https://img.shields.io/npm/v/@goderash/adapter-langgraph.svg)](https://www.npmjs.com/package/@goderash/adapter-langgraph) | [![dl](https://img.shields.io/npm/dw/@goderash/adapter-langgraph.svg)](https://www.npmjs.com/package/@goderash/adapter-langgraph) | LangGraph.js / LangChain.js |

### Python (PyPI)

| Package | Version | Monthly Downloads | Description |
|---|---|---|---|
| [`goderash-sdk`](https://pypi.org/project/goderash-sdk/) | [![pypi](https://img.shields.io/pypi/v/goderash-sdk.svg)](https://pypi.org/project/goderash-sdk/) | [![dl](https://img.shields.io/pypi/dm/goderash-sdk.svg)](https://pypi.org/project/goderash-sdk/) | Core SDK + runtime guards |
| [`goderash-adapter-anthropic`](https://pypi.org/project/goderash-adapter-anthropic/) | [![pypi](https://img.shields.io/pypi/v/goderash-adapter-anthropic.svg)](https://pypi.org/project/goderash-adapter-anthropic/) | [![dl](https://img.shields.io/pypi/dm/goderash-adapter-anthropic.svg)](https://pypi.org/project/goderash-adapter-anthropic/) | Anthropic Messages + tool use |
| [`goderash-adapter-openai`](https://pypi.org/project/goderash-adapter-openai/) | [![pypi](https://img.shields.io/pypi/v/goderash-adapter-openai.svg)](https://pypi.org/project/goderash-adapter-openai/) | [![dl](https://img.shields.io/pypi/dm/goderash-adapter-openai.svg)](https://pypi.org/project/goderash-adapter-openai/) | OpenAI Chat / Responses / Assistants |
| [`goderash-adapter-langgraph`](https://pypi.org/project/goderash-adapter-langgraph/) | [![pypi](https://img.shields.io/pypi/v/goderash-adapter-langgraph.svg)](https://pypi.org/project/goderash-adapter-langgraph/) | [![dl](https://img.shields.io/pypi/dm/goderash-adapter-langgraph.svg)](https://pypi.org/project/goderash-adapter-langgraph/) | LangGraph / LangChain callback |

## Install

```bash
# Python
pip install goderash-sdk

# TypeScript / JavaScript
npm i @goderash/sdk
```

## Try it in 60 seconds

```bash
git clone https://github.com/goderash/goderash && cd goderash

# Start Postgres and run the golden-path demo (Docker required):
./examples/golden_path/quickstart.sh
```

The demo script:
1. Provisions a tenant + API key
2. Emits a full AI agent turn — 7 events — to the ledger
3. Verifies the SHA-256 hash chain (clean)
4. Injects a tamper mid-chain → SOC 2 pack refuses (HTTP 409)
5. Runs `POST /v1/verify` → returns `first_broken_index`
6. Restores the hash and generates a signed SOC 2 ZIP

Sample output:

```
STEP 3 — Verifying the hash chain
  ✓ POST /v1/verify   ok=True  checked=7  [200]

    seq  prev_hash[:12]  →  hash[:12]          event_type
    ──────────────────────────────────────────────────────
     01  000000000000…  →  e0b9f84ccfdc…  agent.turn.started
     02  e0b9f84ccfdc…  →  d2c3656b0fb8…  llm.call.started
     03  d2c3656b0fb8…  →  64ab7ecd24a5…  tool.invoked
     04  64ab7ecd24a5…  →  6061fb7cb7d5…  permission.granted
     05  6061fb7cb7d5…  →  45f363f31ded…  tool.completed
     06  45f363f31ded…  →  6061cac8d781…  llm.call.completed
     07  6061cac8d781…  →  94c51435d718…  agent.turn.completed

STEP 4 — Tamper detection
  ⚠ Corrupting seq=4 (permission.granted) …
  ✗ POST /v1/packs/soc2   [409 CONFLICT]  ← pack refused: chain broken at index 3
  ✗ POST /v1/verify   ok=False  first_broken_index=3  [200]

STEP 5 — SOC 2 Evidence Pack
  ✓ POST /v1/packs/soc2   [200]
    SHA-256:     6f23dfde34a8016cf2649f37…
    Controls:    CC6.1_logical_access, CC7.2_monitoring, CC7.4_incidents
```

## Full development setup

```bash
git clone https://github.com/goderash/goderash && cd goderash
cp .env.example .env
make setup
make dev      # boots Postgres + Redis + control plane on :8000

# In another shell — seed a demo tenant + API key
docker compose -f infra/docker/docker-compose.yml exec core \
  python -m goderash_core.scripts.seed
# → prints a gdr_... API key once. Save it.

# Optional: bring up the dashboard
cd packages/dashboard && pnpm install
GODERASH_API_KEY=gdr_... GODERASH_TENANT=demo pnpm dev
# → http://localhost:3000
```

## Wrap your agent

### Python — drop-in tool wrapper

```python
from goderash_sdk import GoderashClient, wrap_tool

goderash = GoderashClient(api_key="gdr_...", tenant="demo", agent_id="ops-v1")

@wrap_tool(goderash, category="action", confirmation="biometric")
def transfer_money(src: str, dst: str, amount: float) -> dict:
    return {"status": "queued"}

with goderash.turn() as ctx:
    transfer_money("checking", "savings", 100.0, _goderash_context=ctx)
```

### Python — LangGraph callback

```python
from goderash_sdk import GoderashClient
from goderash_adapter_langgraph import GoderashCallback

goderash = GoderashClient(...)
graph.invoke(input, config={"callbacks": [GoderashCallback(goderash)]})
```

### Python — OpenAI Assistants

```python
from goderash_adapter_openai import audit_assistants_run, wrap_openai

wrap_openai(openai_client, goderash=goderash, context=ctx)
run = openai_client.beta.threads.runs.create_and_poll(...)
audit_assistants_run(openai_client, goderash, ctx, run, thread_id=thread.id)
```

### Python — Anthropic Messages

```python
from goderash_adapter_anthropic import wrap_anthropic
wrap_anthropic(anthropic_client, goderash=goderash, context=ctx)
```

### TypeScript

```ts
import { GoderashClient, wrapTool } from '@goderash/sdk'

const goderash = new GoderashClient({ apiKey: '...', tenant: 'demo' })
const ctx = goderash.newContext()
const transfer = wrapTool(goderash, { category: 'action', context: ctx },
  async (src, dst, amount) => ({ status: 'queued' }),
)
await transfer('checking', 'savings', 100)
await goderash.flush()
```

### Runtime guards (Python)

```python
from goderash_sdk.guards import (
    GuardChain, FraudGuard, PermissionMode, PermissionModeGate,
    VelocityLimiter, VelocityRule, ConversationBudget,
)

guards = GuardChain(
    FraudGuard(),
    PermissionModeGate(mode=PermissionMode.DEFAULT, confirm=ask_user),
    VelocityLimiter(rules_by_tool={
        "transfer_money": [
            VelocityRule(window_seconds=3600, max_count=5, label="5/hour"),
            VelocityRule(window_seconds=86400, max_amount=10_000, label="10k/day"),
        ],
    }),
    ConversationBudget(max_tool_calls=20, max_tokens=200_000),
)

decision = guards.evaluate(goderash, ctx, tool_name="transfer_money", amount=500)
if decision.allow:
    transfer_money(...)
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Customer agent (LangGraph, OpenAI Assistants, Anthropic, …)     │
└──────────────────────────────────────┬───────────────────────────┘
                                       │ Goderash SDK + adapter
                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│  Goderash core (FastAPI control plane, multi-tenant)               │
│                                                                   │
│  /v1/events  /v1/verify  /v1/packs/{reg}  /v1/whatif  /v1/admin  │
│                                                                   │
│  Postgres append-only ledger + SHA-256 chain + upcasters         │
│  + 5 compliance pack generators + What-If projector              │
└──────────────────────────────────────────────────────────────────┘
                                       ▲
                                       │ server-rendered
┌──────────────────────────────────────┴───────────────────────────┐
│  @goderash/dashboard (Next.js 14)                                  │
│  /events  /verify  /packs  /whatif  /settings                    │
└──────────────────────────────────────────────────────────────────┘
```

See [docs/architecture.md](docs/architecture.md) for the full picture.

## Repository layout

```
goderash/
├── python/
│   ├── core/                          # FastAPI control plane
│   ├── goderash_sdk/                    # goderash-sdk
│   ├── goderash_adapter_langgraph/      # LangChain callback handler
│   ├── goderash_adapter_openai/         # OpenAI client + Assistants
│   └── goderash_adapter_anthropic/      # Anthropic Messages
├── packages/
│   ├── sdk-ts/                        # @goderash/sdk
│   ├── adapter-langgraph/             # @goderash/adapter-langgraph
│   └── dashboard/                     # @goderash/dashboard (Next.js 14)
├── examples/                          # Runnable end-to-end examples
├── compliance/                        # Pack templates per regulation
├── docs/                              # Architecture, quickstart, guides
├── infra/                             # Docker, k8s, terraform
└── scripts/                           # Dev + release scripts
```

## Compliance packs

Generate evidence for a regulation by `POST`ing to its endpoint:

```bash
curl -X POST http://localhost:8000/v1/packs/soc2 \
  -H "X-Goderash-Api-Key: $GODERASH_API_KEY" \
  -H "X-Goderash-Tenant: $GODERASH_TENANT" \
  -o goderash-soc2.zip
```

Available: `soc2`, `hipaa`, `ffiec`, `finra`, `sec_17a4`. Each ZIP has a
`manifest.json`, `events.json` (the chain-verified events), and
`controls.json` (regulation-specific control evidence).

## What-If

```bash
curl -X POST http://localhost:8000/v1/whatif \
  -H "X-Goderash-Api-Key: $GODERASH_API_KEY" \
  -H "X-Goderash-Tenant: $GODERASH_TENANT" \
  -d '{"policy":{"deny_tools":["transfer_money"]}}'
```

Returns the counterfactual decisions that would have flipped under that
policy — exactly what regulators ask when they say "what would have
happened if you had blocked X?".

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The compliance pack generators emit evidence intended to assist customer
audit programs. They are **not** legal advice and do not by themselves
attest to compliance. Customers remain responsible for obtaining
independent attestations from qualified auditors.
