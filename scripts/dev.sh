#!/usr/bin/env bash
# Convenience script: bring the stack up, run migrations, seed a demo tenant,
# and print the API key for immediate use.

set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[setup] created .env from .env.example"
fi

echo "[setup] starting Postgres + Redis + core…"
docker compose -f infra/docker/docker-compose.yml up -d --build postgres redis core

echo "[setup] waiting for core to be healthy…"
for i in {1..60}; do
  if curl -fsS http://localhost:8000/ready > /dev/null 2>&1; then
    echo "[setup] core is ready"
    break
  fi
  sleep 1
done

echo "[setup] seeding demo tenant + API key…"
docker compose -f infra/docker/docker-compose.yml exec -T core \
  python -m goderash_core.scripts.seed || true

echo ""
echo "Visit http://localhost:8000/docs for the OpenAPI surface."
