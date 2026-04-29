#!/usr/bin/env bash
# Goderash — Golden Path Quickstart
# Starts a local Postgres (Docker required), runs the demo, then tears down.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/infra/docker/docker-compose.yml"

# ── colours ────────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
  BOLD="\033[1m"; GREEN="\033[32m"; YELLOW="\033[33m"; RESET="\033[0m"
else
  BOLD=""; GREEN=""; YELLOW=""; RESET=""
fi

step() { echo -e "\n${BOLD}▶ $*${RESET}"; }
ok()   { echo -e "  ${GREEN}✓${RESET} $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $*"; }

# ── preflight ──────────────────────────────────────────────────────────────────
step "Checking prerequisites"

if ! command -v docker &>/dev/null; then
  echo "  Docker is required. Install it at https://docs.docker.com/get-docker/" >&2
  exit 1
fi
ok "Docker found: $(docker --version | head -1)"

if ! command -v uv &>/dev/null; then
  echo "  uv is required. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi
ok "uv found: $(uv --version)"

# ── start Postgres ─────────────────────────────────────────────────────────────
step "Starting Postgres"
docker compose -f "$COMPOSE_FILE" up -d postgres
ok "Postgres container up"

step "Waiting for Postgres to be ready"
for i in $(seq 1 20); do
  if docker compose -f "$COMPOSE_FILE" exec -T postgres \
       pg_isready -U goderash -q 2>/dev/null; then
    ok "Postgres is ready (${i}s)"
    break
  fi
  if [ "$i" -eq 20 ]; then
    echo "  Postgres did not become ready in 20 s." >&2
    docker compose -f "$COMPOSE_FILE" logs postgres | tail -20 >&2
    exit 1
  fi
  sleep 1
done

# ── install Python deps ────────────────────────────────────────────────────────
step "Installing Python workspace dependencies"
(cd "$REPO_ROOT" && uv sync --package goderash-core --quiet)
ok "Dependencies installed"

# ── run demo ───────────────────────────────────────────────────────────────────
step "Running the golden-path demo"
echo ""

export DATABASE_URL="postgresql+asyncpg://goderash:goderash@localhost:5432/goderash"
export JWT_SECRET="demo-only-jwt-secret-placeholder-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
export ADMIN_API_KEY="gdr_admin_demo_key_for_local_dev_only"

(cd "$REPO_ROOT" && uv run --package goderash-core python examples/golden_path/demo.py)

# ── cleanup ────────────────────────────────────────────────────────────────────
echo ""
warn "Postgres container is still running (reuse for further experiments)."
echo "     Stop it with:  docker compose -f infra/docker/docker-compose.yml down"
