# Deployment

## Local (dev)

```bash
make setup
make dev
```

Brings up Postgres, Redis, and the FastAPI core on `http://localhost:8000`.

## Self-hosted (Docker Compose)

```bash
make dev-bg
make migrate
make seed
```

Data is persisted in the named volumes `postgres-data`, `redis-data`, and
`pack-output`.

## Cloud (Fly / Railway / Render / Fargate)

The control plane is a single stateless container (`infra/docker/Dockerfile.core`)
plus Postgres + Redis. Minimum production checklist:

- Managed Postgres 16+ (with automated backups + PITR)
- Managed Redis 7+
- Egress allowlist to your customers' fetchable endpoints only
- TLS termination at the edge
- WAF in front of `/v1/events` + `/v1/admin/*`
- Secrets from a KMS-backed store (SOPS, Vault, AWS Secrets Manager, Doppler)
- `JWT_SECRET` and `ADMIN_API_KEY` rotated regularly

## VPC self-hosted (for regulated customers)

Deliverables:

- Terraform module under `infra/terraform/` (to be added)
- Helm chart under `infra/k8s/` (to be added)
- Air-gapped install mode (no outbound calls except to the customer's DB + Redis)
- Customer-held signing key for evidence-pack integrity

## Migrations

Forward-only. Applied automatically by the `core` container on boot via
`alembic upgrade head`. In restricted environments, set
`ALEMBIC_SKIP_AUTO_UPGRADE=1` and run migrations from an operator step.

## Observability

- `/metrics` exposes Prometheus counters (when `PROMETHEUS_ENABLED=true`)
- Structured JSON logs via `structlog` on stdout
- Optional Langfuse sink (set `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`)
- Optional OTLP exporter (set `OTEL_ENABLED=true` + `OTEL_EXPORTER_OTLP_ENDPOINT`)

## Backups

- Postgres: nightly `pg_dump` + 7-day PITR is the minimum for audit retention.
- The ledger is self-verifying: after restore, run `POST /v1/verify` for each
  active tenant to confirm chain integrity before resuming ingestion.
