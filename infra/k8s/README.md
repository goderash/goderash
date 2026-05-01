# Goderash on Kubernetes

A minimal, opinionated single-region deployment. Production users should
swap the in-cluster Postgres + Redis for managed services (RDS / Cloud SQL,
ElastiCache / Memorystore) and re-point `core` via `goderash-secrets`.

## Layout

| File | Purpose |
|------|---------|
| `namespace.yaml` | `goderash` namespace + default labels |
| `configmap.yaml` | Non-secret runtime config (env, log level, host, port) |
| `secret.example.yaml` | Template for `JWT_SECRET`, `ADMIN_API_KEY`, DB URLs |
| `postgres.yaml` | Single-replica Postgres 16 + PVC + Service (dev/PoC only) |
| `redis.yaml` | Single-replica Redis 7 + PVC + Service (dev/PoC only) |
| `core.yaml` | Goderash core Deployment + Service (FastAPI on :8000) |
| `migrations.yaml` | One-shot Job that runs `alembic upgrade head` on rollout |
| `dashboard.yaml` | Next.js dashboard Deployment + Service (port 3000) |
| `ingress.yaml` | NGINX-class ingress for `core` and `dashboard` |
| `kustomization.yaml` | Apply everything with one command |

## Apply

```bash
# 1. Create the namespace + secrets out-of-band (do NOT commit secret.yaml)
kubectl apply -f infra/k8s/namespace.yaml
cp infra/k8s/secret.example.yaml infra/k8s/secret.yaml
$EDITOR infra/k8s/secret.yaml          # set JWT_SECRET, ADMIN_API_KEY, DB URLs
kubectl apply -f infra/k8s/secret.yaml

# 2. Apply the rest
kubectl apply -k infra/k8s
```

## Image

The manifests reference `ghcr.io/goderash/goderash-core:latest` and
`ghcr.io/goderash/goderash-dashboard:latest`. Build + push from the repo
root:

```bash
docker build -t ghcr.io/goderash/goderash-core:latest \
  -f infra/docker/Dockerfile.core .
docker push ghcr.io/goderash/goderash-core:latest
```

For the dashboard, see `packages/dashboard/Dockerfile` (add when shipping).

## Production checklist

- [ ] Replace in-cluster Postgres with a managed service
- [ ] Replace in-cluster Redis with a managed service
- [ ] Set non-default `JWT_SECRET` and rotate `ADMIN_API_KEY`
- [ ] Point ingress at a real DNS + TLS cert (cert-manager)
- [ ] Add `HorizontalPodAutoscaler` once load is known
- [ ] Add `NetworkPolicy` to lock down inter-pod traffic
- [ ] Wire `PodDisruptionBudget` for the core deployment
