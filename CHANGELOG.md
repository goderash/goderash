# Changelog

All notable changes to Goderash are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Stateless `_post_async` retries are still TODO; current SDK transport
  surfaces transport errors directly to the caller.

## [0.1.0] — 2026-04-27

### Added

- **Control plane** (`goderash-core`): FastAPI app, multi-tenant ingestion,
  Postgres-backed append-only event ledger with SHA-256 hash chain,
  `UpcasterRegistry` for schema evolution, advisory-lock-serialized
  per-tenant append, and idempotent inserts on `event_id`.
- **Routes**: `POST /v1/events`, `GET /v1/events`, `POST /v1/verify`,
  `GET /v1/packs`, `POST /v1/packs/{regulation}`, `POST /v1/whatif`,
  admin endpoints for tenant + API key issuance.
- **Compliance packs**: SOC 2, HIPAA Security Rule, FFIEC IT Examination
  Handbook, FINRA Rule 4511 / 3110, SEC Rule 17a-4. All build a signed-
  manifest ZIP with chain-verified events.
- **What-If projector**: counterfactual replay against alternate policy
  bundles (velocity caps, deny lists, stricter permission modes); summary +
  diff list.
- **Data contracts**: Bitol-flavored clauses with a stateless enforcer —
  type / required / range / max / min / enum / regex / uuid / datetime /
  monotonic / unique / non_null.
- **Python SDK** (`goderash-sdk`): `GoderashClient`, `GoderashContext`, all
  envelope + payload types, `wrap_tool` / `wrap_llm` / `wrap_agent`.
- **SDK guards** (`goderash_sdk.guards`): `FraudGuard` (lifted from Dashen
  AIR), `PermissionModeGate` (PLAN/DEFAULT/AUTO/STRICT), `VelocityLimiter`
  (in-memory + Redis backends), `ConversationBudget`, `CancellationToken`,
  `GuardChain` for ordered composition.
- **TypeScript SDK** (`@goderash/sdk`): `GoderashClient`, `GoderashContext`, full
  event type surface, `wrapTool` / `wrapLLM` / `wrapAgent`, isomorphic
  hashing.
- **Adapters**:
  - `goderash-adapter-langgraph` (Python) — full LangChain callback handler.
  - `@goderash/adapter-langgraph` (TS) — typed callback handler.
  - `goderash-adapter-openai` (Python) — wrap-once + Assistants run walker.
  - `goderash-adapter-anthropic` (Python) — wrap Messages API + tool_use
    block extraction.
- **Dashboard** (`@goderash/dashboard`): Next.js 14 server-rendered admin UI
  with `/`, `/events`, `/verify`, `/packs`, `/whatif`, `/settings`.
- **Examples**: LangGraph ReAct agent, OpenAI Assistants run, Anthropic
  Messages call, all running end-to-end against the local control plane.
- **Tests**: chain tampering / reordering / missing detection, upcaster
  chain walking, every event type's round-trip, SOC 2 + HIPAA + FFIEC +
  FINRA + 17a-4 pack building, all guards, what-if projection, contract
  enforcement.
- **Tooling**: Apache 2.0 LICENSE + NOTICE, SECURITY.md, CONTRIBUTING.md,
  CLAUDE.md, multi-stage non-root Dockerfile (uid 1001), docker-compose,
  GitHub Actions CI (lint / type / security / tests / Docker), Alembic
  migrations, biome.json, pnpm + uv workspaces, seed script.

### Known limitations

- Integration tests requiring Postgres are skipped unless
  `GODERASH_TEST_DATABASE_URL` is set; `services` block in CI runs them.
- Dashboard has no client-side state; every page is server-rendered. No
  interactive policy editor for What-If yet.
- TS LangGraph adapter is callback-shape-typed but pinned loosely against
  `@langchain/core`; tighten once we commit to a minor version.
- WORM storage for SEC 17a-4 retention is a deployment-tier concern; the
  ledger emits compatible records but the customer's storage layer must
  enforce non-rewritable / non-erasable semantics.
