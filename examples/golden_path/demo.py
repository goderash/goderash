#!/usr/bin/env python3
"""
Goderash — Golden Path Demo
============================
End-to-end walkthrough: provision a tenant, emit a realistic AI agent turn,
verify the hash chain, witness tamper detection, and generate a SOC 2 evidence
pack — all in a single in-process run against a real Postgres database.

Quick start (requires Docker):
    cd goderash
    docker compose -f infra/docker/docker-compose.yml up -d postgres
    uv run --package goderash-core python examples/golden_path/demo.py

Or with a custom Postgres:
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db \
    JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))") \
    ADMIN_API_KEY=gdr_admin_demo_key_for_local_dev_only \
    uv run --package goderash-core python examples/golden_path/demo.py
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import sys
import zipfile
from uuid import uuid4

# ── environment defaults (set before any goderash_core import) ─────────────────
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://goderash:goderash@localhost:5432/goderash",
)
os.environ.setdefault(
    "JWT_SECRET",
    "demo-only-jwt-secret-placeholder-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
)
os.environ.setdefault("ADMIN_API_KEY", "gdr_admin_demo_key_for_local_dev_only")
os.environ.setdefault("GODERASH_ENV", "dev")
os.environ.setdefault("PROMETHEUS_ENABLED", "false")
os.environ.setdefault("GODERASH_LOG_LEVEL", "WARNING")

import httpx
from sqlalchemy import text

import goderash_core.db as _db
from goderash_core.db import Base
from goderash_core.main import app  # module-level app; engine created on first request
from goderash_core.models import event as _  # noqa: register EventRow with Base.metadata
from goderash_core.models import tenant as __  # noqa: register Tenant, ApiKey

# ── terminal colours ───────────────────────────────────────────────────────────
_TTY = sys.stdout.isatty()
RESET = "\033[0m" if _TTY else ""
BOLD  = "\033[1m" if _TTY else ""
DIM   = "\033[2m" if _TTY else ""
GREEN = "\033[32m" if _TTY else ""
RED   = "\033[31m" if _TTY else ""
YELLOW = "\033[33m" if _TTY else ""
CYAN  = "\033[36m" if _TTY else ""

ADMIN_KEY = os.environ["ADMIN_API_KEY"]


def _banner() -> None:
    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗")
    print(      "║  GODERASH — Golden Path Demo                                 ║")
    print(      "║  Audit & governance fabric for regulated AI agents           ║")
    print(f"╚══════════════════════════════════════════════════════════════╝{RESET}\n")


def _step(n: int, title: str) -> None:
    print(f"\n{BOLD}STEP {n} — {title}{RESET}")


def _ok(msg: str)   -> None: print(f"  {GREEN}✓{RESET} {msg}")
def _fail(msg: str) -> None: print(f"  {RED}✗{RESET} {msg}")
def _warn(msg: str) -> None: print(f"  {YELLOW}⚠{RESET} {msg}")
def _dim(msg: str)  -> None: print(f"  {DIM}{msg}{RESET}")


# ── demo ───────────────────────────────────────────────────────────────────────

async def main() -> None:
    _banner()

    # Create tables (idempotent; safe to run on an existing DB).
    engine = _db.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _dim("DB tables ready.")

    # Unique tenant ID so repeated runs never collide.
    tenant_id = f"acme-finance-{uuid4().hex[:6]}"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://demo.goderash") as c:

        # ── Step 1: Provisioning ─────────────────────────────────────────────
        _step(1, "Provisioning")

        r = await c.post(
            "/v1/admin/tenants",
            headers={"X-Goderash-Api-Key": ADMIN_KEY},
            json={"id": tenant_id, "display_name": "Acme Finance AI"},
        )
        assert r.status_code == 201, f"create tenant: {r.text}"
        _ok(f"Tenant created    {BOLD}{tenant_id}{RESET}")

        r = await c.post(
            "/v1/admin/keys",
            headers={"X-Goderash-Api-Key": ADMIN_KEY},
            json={"tenant_id": tenant_id, "label": "demo-key"},
        )
        assert r.status_code == 201, f"create key: {r.text}"
        api_key = r.json()["api_key"]
        _ok(f"API key issued    {DIM}{api_key[:16]}...{RESET}")

        auth = {"X-Goderash-Api-Key": api_key, "X-Goderash-Tenant": tenant_id}

        # ── Step 2: Emit a full agent turn (7 events) ────────────────────────
        _step(2, "Emitting a full agent turn  (7 events)")

        conv_id = str(uuid4())
        turn_id = str(uuid4())
        base_env = {
            "tenant_id": tenant_id,
            "agent_id": "portfolio-advisor-v2",
            "conversation_id": conv_id,
            "turn_id": turn_id,
            "schema_version": 1,
        }

        events = [
            {**base_env, "payload": {
                "event_type": "agent.turn.started",
                "user_message": (
                    "Show me my portfolio balance and flag suspicious transactions."
                ),
            }},
            {**base_env, "payload": {
                "event_type": "llm.call.started",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens_estimated": 312,
                "tools_offered": ["check_balance", "list_transactions", "flag_transaction"],
            }},
            {**base_env, "payload": {
                "event_type": "tool.invoked",
                "tool_name": "check_balance",
                "tool_category": "query",
                "input_args_hash": hashlib.sha256(b'{"account_id":"acct_001"}').hexdigest(),
                "input_args_preview": {"account_id": "acct_001"},
                "confirmation_type": "none",
            }},
            {**base_env, "payload": {
                "event_type": "permission.granted",
                "tool_name": "check_balance",
                "source": "rule",
                "reason": "read-only query tools are auto-approved",
            }},
            {**base_env, "payload": {
                "event_type": "tool.completed",
                "tool_name": "check_balance",
                "success": True,
                "duration_ms": 42,
                "result_hash": hashlib.sha256(b'{"balance":24500.00}').hexdigest(),
                "result_preview": {"balance_usd": 24500.00},
            }},
            {**base_env, "payload": {
                "event_type": "llm.call.completed",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 389,
                "output_tokens": 94,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "duration_ms": 1241,
                "stop_reason": "end_turn",
            }},
            {**base_env, "payload": {
                "event_type": "agent.turn.completed",
                "assistant_message": (
                    "Your portfolio balance is $24,500. No suspicious transactions "
                    "detected in the last 30 days."
                ),
                "input_tokens": 389,
                "output_tokens": 94,
                "tool_calls_made": 1,
                "duration_ms": 1283,
                "stop_reason": "end_turn",
            }},
        ]

        r = await c.post("/v1/events", headers=auth, json={"events": events})
        assert r.status_code == 202, f"ingest: {r.text}"
        ingest = r.json()
        _ok(f"POST /v1/events   accepted={ingest['accepted']}  [{r.status_code}]")
        for ev in events:
            _dim(f"  {ev['payload']['event_type']}")

        # ── Step 3: Verify the hash chain (clean) ────────────────────────────
        _step(3, "Verifying the hash chain")

        r = await c.post("/v1/verify", headers=auth, json={})
        assert r.status_code == 200, f"verify: {r.text}"
        v = r.json()
        assert v["ok"] is True, f"chain broken on clean data: {v}"
        _ok(f"POST /v1/verify   ok={v['ok']}  checked={v['checked']}  [{r.status_code}]")
        _dim("All 7 events are cryptographically intact.")

        # Fetch and display chain fingerprint.
        r2 = await c.get("/v1/events", headers=auth, params={"limit": 7})
        rows = r2.json()
        _dim("")
        _dim("  seq  prev_hash[:12]  →  hash[:12]          event_type")
        _dim("  ──────────────────────────────────────────────────────")
        for row in rows:
            p = row["prev_hash"][:12]
            h = row["hash"][:12]
            _dim(f"   {row['sequence_no']:02d}  {p}…  →  {h}…  {row['event_type']}")

        # ── Step 4: Tamper and try to generate a pack ────────────────────────
        _step(4, "Tamper detection")

        # Corrupt the hash of event at index 3 (permission.granted).
        target_seq = rows[3]["sequence_no"]
        original_hash = rows[3]["hash"]
        _warn(f"Corrupting seq={target_seq} ({rows[3]['event_type']}) …")

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE events"
                    " SET hash = 'TAMPERED00000000000000000000000000000000000000000000000000000000'"
                    " WHERE sequence_no = :seq AND tenant_id = :tid"
                ),
                {"seq": target_seq, "tid": tenant_id},
            )

        # Pack generation should refuse a broken chain (HTTP 409).
        r = await c.post("/v1/packs/soc2", headers=auth, json={})
        assert r.status_code == 409, f"expected 409 on tampered chain, got {r.status_code}: {r.text}"
        err = r.json()
        _fail(
            f"POST /v1/packs/soc2   [{r.status_code} CONFLICT]"
            f"  ← pack refused: chain broken at index {err['detail']['first_broken_index']}"
        )
        _dim("Evidence pack cannot be generated from a tampered ledger.")

        # Verify also flags the tamper.
        r = await c.post("/v1/verify", headers=auth, json={})
        v = r.json()
        assert v["ok"] is False
        _fail(
            f"POST /v1/verify   ok={v['ok']}"
            f"  first_broken_index={v['first_broken_index']}  [{r.status_code}]"
        )

        # Restore the correct hash so we can proceed.
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE events SET hash = :h"
                    " WHERE sequence_no = :seq AND tenant_id = :tid"
                ),
                {"h": original_hash, "seq": target_seq, "tid": tenant_id},
            )
        _dim("Hash restored.")

        # Chain is clean again.
        r = await c.post("/v1/verify", headers=auth, json={})
        v = r.json()
        assert v["ok"] is True
        _ok(f"POST /v1/verify   ok={v['ok']}  checked={v['checked']}  [{r.status_code}]  ← restored")

        # ── Step 5: SOC 2 evidence pack ──────────────────────────────────────
        _step(5, "SOC 2 Evidence Pack")

        r = await c.post("/v1/packs/soc2", headers=auth, json={})
        assert r.status_code == 200, f"soc2 pack: {r.status_code} {r.text}"

        pack_sha256 = r.headers["x-goderash-pack-sha256"]
        event_count = r.headers["x-goderash-pack-event-count"]
        filename    = r.headers.get("content-disposition", "").split('"')[1]

        _ok(f"POST /v1/packs/soc2   [{r.status_code}]")
        _dim(f"  Filename:    {filename}")
        _dim(f"  SHA-256:     {pack_sha256}")
        _dim(f"  Events:      {event_count}")

        zf = zipfile.ZipFile(io.BytesIO(r.content))
        _dim(f"  ZIP files:   {', '.join(zf.namelist())}")

        manifest = json.loads(zf.read("manifest.json"))
        controls = json.loads(zf.read("controls.json"))
        _dim(f"  chain_verified: {manifest['chain_verified']}")
        _dim(f"  Controls:    {', '.join(controls.keys())}")

        # Show one control in detail.
        cc61 = controls.get("CC6.1_logical_access", {})
        _dim(f"  CC6.1 — allowed: {cc61.get('allowed_actions')}"
             f"  denied: {cc61.get('denied_actions')}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{GREEN}✓  Demo complete.{RESET}\n")
    print("What you just saw:")
    print("  1.  Tenant + API key provisioned — one round-trip, keys hashed at rest.")
    print("  2.  7 events emitted — full AI agent turn with LLM + tool call lifecycle.")
    print("  3.  SHA-256 hash chain verified across all events — cryptographically intact.")
    print("  4.  Tamper injected mid-chain — SOC 2 pack refused (409) and verify returned")
    print("      first_broken_index showing exactly where integrity failed.")
    print("  5.  Chain restored — SOC 2 ZIP generated: manifest + events + controls.")
    print()
    print(f"  Next: {DIM}try HIPAA, FFIEC, FINRA, or sec_17a4 packs — same one-liner.{RESET}\n")

    await _db.dispose_engine()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"\n{RED}ASSERTION FAILED:{RESET} {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"\n{RED}ERROR:{RESET} {exc}", file=sys.stderr)
        raise
