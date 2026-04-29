# Concepts

## Event

A single, immutable record of something that happened in an agent. Always
scoped to a `tenant_id`, an `agent_id`, a `conversation_id`, and a `turn_id`.
An event is typed (e.g. `tool.invoked`, `llm.call.completed`) and has a
discriminated payload.

## Envelope

The transport unit. Wraps a typed payload with provenance fields (IDs,
timestamps) and — after the ledger stores it — chain fields (`prev_hash`,
`hash`, `sequence_no`, `recorded_at`).

## Ledger

The Postgres `events` table. Append-only, hash-chained, per-tenant ordered.
Never mutated, never downgraded. Backups include the last-verified chain
root so that restoring from backup is itself verifiable.

## Hash chain

Each event's `hash = SHA-256(prev_hash || canonical_json(payload))`. The
first event in a tenant's stream uses the genesis sentinel (`"0" * 64`).
Any in-place mutation, removal, or reordering breaks the chain and is
detected by the verify endpoint.

## Upcaster

A forward migration for a single event type's payload shape. Register one
when you bump a schema version; the ledger calls it at read time to present
older rows in the current shape. Rows are never rewritten.

## Tenant

The hard isolation boundary. One API key = one tenant. One FDE integration =
one tenant. Every query filters on `tenant_id`. Cross-tenant reads are
structurally impossible through the public API.

## Context

A runtime-scoped identity object (`tenant_id`, `agent_id`, `conversation_id`,
`turn_id`). Every `emit()` call takes a context; contexts are created with
`client.new_context()` or `client.turn()` / `client.async_turn()`.

## Compliance pack

A generated evidence bundle for a specific regulation (SOC2, HIPAA, FFIEC,
FINRA, SEC 17a-4). A pack's generator declares which event types it needs,
queries the ledger for a time range, renders templates, and ships a signed
ZIP + manifest. Packs are reproducible: given the same ledger state, the
same pack is generated bit-for-bit (modulo timestamps).

## What-If projector *(planned)*

Replays a tenant's history under an alternate policy set (e.g. tighter
velocity limits, a new fraud guard rule) and produces a counterfactual
ledger. Regulators ask: "if you had done X, what would have happened?" —
this is how we answer deterministically.

## Data contract

A machine-checkable schema + invariants expected at some boundary
(tool input, tool output, LLM response). Violations emit
`contract.violated` events with a `blame_chain` — the sequence of events
that produced the bad value, so an operator can trace the fault to the
component that introduced it.

## Blame chain

The ordered list of `event_id`s that contributed to the current state at
the point of a contract violation. Used for post-incident forensics and
for the What-If projector's delta output.

## Permission mode

The runtime posture for the agent's action surface:

| Mode | Behavior |
|---|---|
| `PLAN` | Dry-run. Action tools are blocked; reads allowed. |
| `DEFAULT` | Ask the user on each action; reads auto-approved. |
| `AUTO` | Pre-authorized by rule; only explicit denies block. |
| `STRICT` | Confirm everything, including reads. |

Every decision (granted or denied) is emitted to the ledger as
`permission.granted` / `permission.denied`.

## Velocity counter

Per-user, per-tool, per-time-window counters stored in Redis. When a
threshold is crossed, an action is denied and a `permission.denied` event
with `source="velocity"` is written. Thresholds are tenant-configured.

## Cancellation window

A short delay between "agent queued the action" and "action is irreversible",
during which a user's `/stop` can revoke it. Surfaces in the ledger as
`permission.denied` with `source="user"`.

## Conversation budget

Hard caps per conversation: total tokens, total tool calls, total duration.
Exceeding a budget denies the next action, not retroactively — prior work
stands in the ledger.
