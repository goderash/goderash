"""End-to-end: create tenant + key, ingest a batch, verify chain, generate packs."""

from __future__ import annotations

import os
from typing import AsyncIterator
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    "postgresql" not in os.environ.get("GODERASH_TEST_DATABASE_URL", ""),
    reason="requires a real Postgres (set GODERASH_TEST_DATABASE_URL)",
)


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    from goderash_core.main import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_full_roundtrip(client: httpx.AsyncClient) -> None:
    admin_key = os.environ["ADMIN_API_KEY"]
    tenant_id = f"t-{uuid4().hex[:8]}"

    r = await client.post(
        "/v1/admin/tenants",
        headers={"X-Goderash-Api-Key": admin_key},
        json={"id": tenant_id, "display_name": "Integration Test Co"},
    )
    assert r.status_code == 201, r.text

    r = await client.post(
        "/v1/admin/keys",
        headers={"X-Goderash-Api-Key": admin_key},
        json={"tenant_id": tenant_id, "label": "test"},
    )
    assert r.status_code == 201
    api_key = r.json()["api_key"]

    events = [
        {
            "tenant_id": tenant_id,
            "agent_id": "a1",
            "conversation_id": "c1",
            "turn_id": "u1",
            "schema_version": 1,
            "payload": {"event_type": "agent.turn.started", "user_message": "hi"},
        },
        {
            "tenant_id": tenant_id,
            "agent_id": "a1",
            "conversation_id": "c1",
            "turn_id": "u1",
            "schema_version": 1,
            "payload": {
                "event_type": "tool.invoked",
                "tool_name": "check_balance",
                "tool_category": "query",
                "input_args_hash": "a" * 64,
            },
        },
        {
            "tenant_id": tenant_id,
            "agent_id": "a1",
            "conversation_id": "c1",
            "turn_id": "u1",
            "schema_version": 1,
            "payload": {
                "event_type": "tool.completed",
                "tool_name": "check_balance",
                "success": True,
                "duration_ms": 5,
                "result_hash": "b" * 64,
            },
        },
    ]
    r = await client.post(
        "/v1/events",
        headers={"X-Goderash-Api-Key": api_key, "X-Goderash-Tenant": tenant_id},
        json={"events": events},
    )
    assert r.status_code == 202, r.text
    assert r.json()["accepted"] == 3

    r = await client.post(
        "/v1/verify",
        headers={"X-Goderash-Api-Key": api_key, "X-Goderash-Tenant": tenant_id},
        json={},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["checked"] == 3
    assert body["first_broken_index"] is None

    # Every registered pack must build successfully against this ledger.
    for regulation in ("soc2", "hipaa", "ffiec", "finra", "sec_17a4"):
        r = await client.post(
            f"/v1/packs/{regulation}",
            headers={"X-Goderash-Api-Key": api_key, "X-Goderash-Tenant": tenant_id},
            json={},
        )
        assert r.status_code == 200, f"{regulation}: {r.status_code} {r.text}"
        assert r.headers["content-type"] == "application/zip"
        assert int(r.headers["x-goderash-pack-event-count"]) >= 3
        assert r.headers["x-goderash-regulation"] == regulation

    # What-If: pass-through policy → zero diffs.
    r = await client.post(
        "/v1/whatif",
        headers={"X-Goderash-Api-Key": api_key, "X-Goderash-Tenant": tenant_id},
        json={"policy": {}},
    )
    assert r.status_code == 200
    assert r.json()["diff_count"] == 0
