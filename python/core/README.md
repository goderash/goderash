# goderash-core

**Goderash control plane — append-only audit ledger for regulated AI agents.**

FastAPI service with:
- SHA-256 hash-chained event ledger (append-only, tamper-evident, multi-tenant)
- Compliance pack generators: SOC 2, HIPAA, FFIEC, FINRA, SEC Rule 17a-4
- What-If counterfactual projector
- Data-contract enforcement
- Admin API: tenant + API key management

## Quickstart (Docker)

```bash
git clone https://github.com/goderash/goderash && cd goderash
docker compose -f infra/docker/docker-compose.yml up -d postgres
uv run --package goderash-core python examples/golden_path/demo.py
```

## Self-host

```bash
pip install goderash-core

DATABASE_URL=postgresql+asyncpg://... \
JWT_SECRET=... \
ADMIN_API_KEY=gdr_admin_... \
goderash-core
# → FastAPI on :8000
```

## API surface

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/events` | Ingest a batch of events (idempotent) |
| GET  | `/v1/events` | Query events for the authenticated tenant |
| POST | `/v1/verify` | Re-verify the SHA-256 hash chain |
| POST | `/v1/packs/{reg}` | Generate signed evidence ZIP (soc2, hipaa, ffiec, finra, sec_17a4) |
| POST | `/v1/whatif` | Counterfactual projection under alternate policy |
| GET  | `/health` | Liveness probe |
| GET  | `/ready` | Readiness probe (DB reachable) |

## Links

- [GitHub](https://github.com/goderash/goderash)
- [Website](https://goderash.com)
- [Python SDK](https://pypi.org/project/goderash-sdk/)
