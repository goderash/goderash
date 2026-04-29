# Contributing to Goderash

## Golden rules

1. **Never mutate event history.** Schema changes → register an upcaster.
2. **Never skip tenant filters.** Every query scopes to `tenant_id`.
3. **Never log event payloads.** Payloads live in the ledger; logs carry IDs only.
4. **Every PR includes tests.** Coverage gate is 80% — it will not be lowered.

## Dev workflow

```bash
make setup        # one-time
make dev          # start stack
make test         # run tests
make lint type    # checks
```

## Commit style

Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `ci:`.

## Adding an event type

1. Add the Pydantic model to `python/core/src/goderash_core/events/types.py`.
2. Add it to the `GoderashEvent` discriminated union.
3. Add a round-trip JSON test under `python/core/tests/unit/test_events.py`.
4. If this is a breaking change to an existing type, register an upcaster in `python/core/src/goderash_core/ledger/upcast.py` and keep the old version in `events/archive/`.

## Adding a compliance pack

1. Subclass `PackGenerator` in `python/core/src/goderash_core/packs/<regulation>.py`.
2. Declare `required_event_types`.
3. Implement `collect(tenant_id, start, end)` and `render() -> Artifact`.
4. Add templates under `compliance/templates/<regulation>/`.
5. Add a generator test with a known-good ledger fixture.

## Adding a framework adapter

1. Create a sub-package under `packages/adapter-<framework>/` (TS) or `python/goderash_adapter_<framework>/` (Python).
2. Implement the framework's native callback/instrumentation protocol.
3. Translate callbacks into `GoderashClient.emit()` calls — never bypass the client.
4. Add an end-to-end example under `examples/<framework>-agent/`.

## Security

Report vulnerabilities privately to `security@goderash.dev` (set up before public launch).
