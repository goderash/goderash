# Changelog

All notable changes to Goderash are documented in this file. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Self-serve identity layer** — Sprint 1 of the productization push.
  - `users` and `memberships` tables (Alembic `0002_users_and_memberships`).
  - Argon2id password hashing (`security.passwords`) and HS256 session JWTs
    with `access` / `refresh` token kinds (`security.tokens`).
  - `POST /v1/auth/signup` — atomically creates the user, a tenant, an
    `owner` membership, and the first API key; returns the raw key + a
    fresh access/refresh pair.
  - `POST /v1/auth/login` — email + password → access/refresh pair; runs a
    decoy verify on missing-user paths so timing doesn't leak existence.
  - `POST /v1/auth/refresh` — trades a refresh token for a fresh pair.
  - `POST /v1/auth/logout` — stateless (client discards tokens).
  - `GET  /v1/auth/me` — returns the current user + all tenant memberships.
  - `GET    /v1/orgs/{tenant_id}/keys`, `POST` to issue, `DELETE` to revoke
    — session-authenticated, scoped to the membership of the acting user;
    returns 404 (not 403) on cross-tenant access to avoid existence leaks.
  - 12 new unit tests; full suite stays green at 51/51.

- **Billing, usage metering, and webhooks** — Sprint 2.
  - Alembic `0003_billing_and_webhooks` adds `plan`, `monthly_event_quota`,
    `stripe_customer_id`, `stripe_subscription_id` to `tenants`, and creates
    the `webhook_endpoints` table.
  - Hobby plan hard quota (10k events/month) enforced at ingest with a `402`
    and upgrade prompt; paid plans record overages for Stripe metered billing.
  - Redis-backed usage counter (`goderash:usage:{tenant}:{YYYY-MM}`, 40-day TTL)
    with DB fallback for billing disputes.
  - Stripe integration (`billing/service.py`): `create_stripe_customer`,
    `create_stripe_subscription`, `report_stripe_usage` — all async via
    `asyncio.to_thread`, fire-and-optional, never fail the main request.
  - `GET /v1/billing/usage` returns current-period events, quota, and overage.
  - `POST /v1/billing/stripe-webhook` handles `subscription.updated` /
    `subscription.deleted` events; signature verified with `stripe.WebhookEndpoint`.
  - Outbound webhooks (`webhooks/dispatcher.py`): HMAC-SHA256 signed payloads
    (`X-Goderash-Signature: sha256=<hex>`), `asyncio.create_task` fire-and-forget,
    exponential-backoff retries on 5xx, `last_status` written in a fresh session.
  - `chain.broken` webhook fired from `POST /v1/verify` when integrity fails.
  - `quota.warning` webhook fired at 80% quota during ingest.
  - `GET/POST/DELETE /v1/orgs/{tenant_id}/webhooks` — manage webhook endpoints
    (Startup+ only, 402 on Hobby); `hmac_secret` returned once at creation.
  - 22 new unit tests (quota logic, HMAC signing, `subscribes_to`); all 73 pass.

- **SDK transport retries** — Sprint 1 / Task 2.
  - Both `GoderashClient._post` (sync) and `_post_async` (async) now retry up to
    3 times on retryable failures (429, 5xx, network/transport errors).
  - Full-jitter exponential backoff: `sleep = uniform(0, min(0.5 × 2ⁿ, 10s))`.
  - Batch payload is serialized once before the loop; server-side `event_id` dedup
    makes all retries safe to re-send.
  - Non-retryable 4xx errors (except 429) propagate immediately without retrying.
  - `time.sleep` in the sync path; `asyncio.sleep` in the async path.
  - 10 new unit tests (`test_client_retry.py`) + 6 new TypeScript tests; all green.

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
