# Security

## Threat model

Primary threats we defend against:

1. **Tampering with audit history** — mitigated by the SHA-256 hash chain and
   the `/v1/verify` endpoint. Any in-place mutation, deletion, or reorder is
   detectable.
2. **Cross-tenant leak** — every query filters on `tenant_id` and every API
   key binds to exactly one tenant. Admin key is the only boundary-crossing
   surface and is not issued to customers.
3. **Replay / ingestion spoofing** — API key over HTTPS; idempotent on
   `event_id` so replays do not duplicate; per-tenant advisory lock ensures
   chain extension is serialized.
4. **Secrets in the ledger** — payloads are expected to be redacted by the
   SDK. Tool args are hashed, not stored raw, unless the caller explicitly
   sets `include_preview=True`.
5. **Denial of service** — batch size capped (`MAX_EVENT_BATCH_SIZE`),
   payload size capped (`MAX_EVENT_PAYLOAD_BYTES`), per-tenant rate-limited.

## What Goderash is not

- **Not an ATO.** Goderash produces evidence; the certification is still
  between the customer and their auditor.
- **Not a secrets manager.** Don't send secrets as payloads.
- **Not a model firewall.** Pair Goderash with a runtime guardrail (Bastion
  planned; today: dashen-air security stack patterns in the SDK).

## Data handling

- API keys are stored as SHA-256 digests; raw keys are returned once at
  issue time and never again.
- Event payloads are stored as JSONB plus a canonical UTF-8 string used
  for hashing. Both are encrypted at rest via the managed Postgres's
  disk encryption.
- Backups must be encrypted at rest and access-controlled; restoring from
  backup should be followed by a full chain verification.

## Reporting a vulnerability

Email `security@goderash.dev` with a clear description and, if possible, a
reproducer. We'll respond within 2 business days. Please do not open
public issues for security-sensitive findings.

## Responsible disclosure window

We commit to:

- Acknowledge within 2 business days
- Triage and initial impact assessment within 5 business days
- Fix in a private branch and coordinate disclosure before public release
