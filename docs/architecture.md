# Architecture

## North star

Goderash is a thin, type-safe fabric between AI agents and the auditors who
have to sign off on them. Every meaningful moment in an agent's execution —
a tool invocation, an LLM call, a permission decision, a contract violation —
becomes an immutable, hash-chained event in a multi-tenant ledger. From those
events we can derive:

1. A tamper-evident timeline regulators trust.
2. Deterministic replays (What-If) under alternate policies.
3. Evidence packs pre-shaped for SOC2, HIPAA, GLBA, FFIEC, FINRA, SEC 17a-4.

## Components

```
┌─────────────────────────────────────────────────────────────┐
│  Customer agent (LangGraph / OpenAI Assistants / Claude     │
│  SDK / LangChain / AutoGen / bespoke)                       │
└─────────────────────────────┬───────────────────────────────┘
                              │ emits via
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Goderash SDK (Python / TypeScript)                           │
│   - wrap_tool / wrap_llm / wrap_agent                       │
│   - GoderashClient buffers + batches + retries                │
│   - Framework adapters (LangGraph, OpenAI Assistants, …)    │
└─────────────────────────────┬───────────────────────────────┘
                              │ HTTPS POST /v1/events (batched)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Goderash Core (FastAPI, Python 3.12)                         │
│                                                             │
│  ┌─────────────────────┐  ┌───────────────────────────────┐ │
│  │  API routes         │  │  Auth (API key, tenant-scoped)│ │
│  │  /v1/events         │  │  Multi-tenant isolation       │ │
│  │  /v1/verify         │  │  Rate limiting (slowapi)      │ │
│  │  /v1/admin/*        │  └───────────────────────────────┘ │
│  └─────────┬───────────┘                                    │
│            │                                                │
│  ┌─────────▼────────────────────────────────────────────┐   │
│  │  Event Ledger                                        │   │
│  │  - Postgres append-only (events table)               │   │
│  │  - SHA-256 hash chain (prev_hash, hash)              │   │
│  │  - per-tenant advisory lock on append                │   │
│  │  - idempotent on event_id                            │   │
│  │  - UpcasterRegistry for schema evolution             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Compliance Pack Engine (planned)                   │    │
│  │  - SOC2, HIPAA, FFIEC, FINRA, SEC 17a-4 templates   │    │
│  │  - Signed ZIP + manifest                            │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  What-If Projector (planned)                        │    │
│  │  - Replay tenant history under alternate policies   │    │
│  │  - Emit counterfactual ledger for side-by-side diff │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## The event model

Every event carries:

| Field | Purpose |
|---|---|
| `event_id` (UUID) | Idempotency key for ingestion |
| `tenant_id` | Hard isolation boundary |
| `agent_id` | Which agent produced this |
| `conversation_id` + `turn_id` | Trace locality within a tenant |
| `parent_event_id` | Causal chain within a turn |
| `sequence_no` | Monotonic per-tenant ordering |
| `schema_version` | Forward-compatible evolution |
| `event_type` | Discriminator for the payload union |
| `occurred_at` | SDK-side timestamp |
| `recorded_at` | Ledger-side timestamp |
| `payload` | Typed event content (JSON) |
| `payload_canonical` | Deterministic JSON used for hashing |
| `prev_hash` / `hash` | SHA-256 chain |

**Event types (v1):**

- `agent.turn.started`, `agent.turn.completed`
- `tool.invoked`, `tool.completed`, `tool.failed`
- `llm.call.started`, `llm.call.completed`
- `permission.granted`, `permission.denied`
- `contract.violated`

The set is intentionally small: one type added without discipline is a
regulator question we can't answer deterministically later. Every addition
needs a test + a migration plan.

## The append path

```
POST /v1/events
   ├─ auth: validate API key → tenant_id
   ├─ reject cross-tenant envelopes (403)
   ├─ EventLedger.append_many(tenant_id, envelopes):
   │    ├─ pg_advisory_xact_lock(tenant_lock_key(tenant_id))
   │    ├─ read head_hash and head_sequence_no for tenant
   │    ├─ for each envelope:
   │    │    ├─ canonical_json(payload) = sorted-keys UTF-8
   │    │    ├─ hash = SHA-256(prev_hash || canonical_json)
   │    │    └─ stage insert row (event_id, sequence_no, …)
   │    └─ INSERT ... ON CONFLICT DO NOTHING  (idempotent)
   └─ return 202 with accepted count + first/last event_id
```

Advisory lock scope: one transaction, one tenant. It serializes chain
extension for that tenant only — other tenants are unaffected.

## Verification

`POST /v1/verify` reads the tenant's events in sequence order and runs
`verify_chain`. It returns `{ok, checked, first_broken_index}`. Used for:

- Periodic integrity checks
- Pre-evidence-pack validation
- Customer self-service audit

## Schema evolution

When an event type needs a new field or a renamed one:

1. Bump `schema_version` on the new class (e.g., `ToolInvokedV2`).
2. Leave the old class and model in place.
3. Register an upcaster in `ledger/upcast.py`:

   ```python
   @registry.register(from_version=1, to_version=2, event_type="tool.invoked")
   def upcast(p: dict) -> dict:
       p["tool_category"] = "query"   # default for historical rows
       return p
   ```

4. At read time, older rows are transformed forward. Raw rows are never
   mutated — the ledger's immutability guarantee survives refactors.

## Multi-tenancy

- Every API key binds to exactly one tenant.
- Every query filters by `tenant_id`.
- The `X-Goderash-Tenant` header must match the key's tenant (or omit it).
- The admin API key (`ADMIN_API_KEY`) can act on any tenant via the header.

## Security stack (adapted from Dashen AIR)

Planned runtime guards at the tool boundary (SDK-side):

1. Fraud guard (regex + heuristics) on user input
2. Slash command short-circuit
3. Permission-mode gate (`PLAN` / `DEFAULT` / `AUTO` / `STRICT`)
4. Velocity limits (per-tool, per-user, per-tenant)
5. Cancellation window (`/stop`)
6. Conversation budget
7. Fraud guard (post-tool) for action escalation

These each emit their own `permission.denied` / `permission.granted` events
so the ledger captures *why* an action was or wasn't taken.

## What's not in v1 (but is on the roadmap)

- Compliance pack generator (SOC2/HIPAA/FFIEC): scaffold exists; template
  content and signing flow pending.
- What-If projector: replay tenant history under alternate policies.
- Data-contract enforcement: full Bitol integration from the wk-7 work.
- CQRS projections: read-model workers for usage metering, cost reporting.
- Dashboard UI: Next.js app under `packages/dashboard/` is scaffolded but
  not populated in v1.
- Runtime guards SDK helpers: velocity/fraud-guard in the Python SDK.

## Why Postgres (not Kafka, not a chain)

- Strong ACID semantics for the per-tenant advisory lock.
- JSONB + indexes cover every query shape we need today.
- Auditors recognize it. Kafka logs are hard to re-verify under pressure.
- At the scale where Postgres cracks, we can shard per-tenant with zero
  code change to the SDK or ingestion path.

If a customer's regulator insists on distributed-ledger storage, we can
attach a second sink (Fabric, QLDB, Merkle proofs) without changing the
primary path.
