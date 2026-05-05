"""Transport retry logic — unit tests.

Mocks httpx at the transport layer via respx so no real network is needed.
asyncio.sleep / time.sleep are patched to instant to keep tests fast.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from goderash_sdk import GoderashClient


def _make_client(batch_size: int = 1000) -> GoderashClient:
    return GoderashClient(
        api_key="gdr_test",
        tenant="test-tenant",
        endpoint="http://fake",
        batch_size=batch_size,
    )


def _emit_one(client: GoderashClient) -> None:
    ctx = client.new_context()
    client.emit(ctx, {"event_type": "agent.turn.started", "user_message": "ping"})


# ── async (flush) ───────────────────────────────────────────────────────────

@respx.mock
async def test_async_succeeds_first_attempt():
    route = respx.post("http://fake/v1/events").mock(
        return_value=httpx.Response(202, json={"accepted": 1})
    )
    client = _make_client()
    _emit_one(client)
    await client.flush()
    assert route.call_count == 1


@respx.mock
async def test_async_retries_once_on_503_then_succeeds(monkeypatch: pytest.MonkeyPatch):
    async def fast_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    responses = iter([httpx.Response(503, text="down"), httpx.Response(202)])
    route = respx.post("http://fake/v1/events").mock(
        side_effect=lambda _req: next(responses)
    )

    client = _make_client()
    _emit_one(client)
    await client.flush()

    assert route.call_count == 2


@respx.mock
async def test_async_exhausts_retries_and_raises(monkeypatch: pytest.MonkeyPatch):
    async def fast_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    route = respx.post("http://fake/v1/events").mock(
        return_value=httpx.Response(503, text="down")
    )

    client = _make_client()
    _emit_one(client)

    with pytest.raises(httpx.HTTPStatusError):
        await client.flush()

    assert route.call_count == 4  # 1 initial + 3 retries


@respx.mock
async def test_async_does_not_retry_400():
    route = respx.post("http://fake/v1/events").mock(
        return_value=httpx.Response(400, text="bad request")
    )

    client = _make_client()
    _emit_one(client)

    with pytest.raises(httpx.HTTPStatusError):
        await client.flush()

    assert route.call_count == 1  # no retries on 4xx


@respx.mock
async def test_async_retries_on_network_error(monkeypatch: pytest.MonkeyPatch):
    async def fast_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    call_count = 0

    def side_effect(_req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectError("connection refused")
        return httpx.Response(202)

    route = respx.post("http://fake/v1/events").mock(side_effect=side_effect)

    client = _make_client()
    _emit_one(client)
    await client.flush()

    assert route.call_count == 2


@respx.mock
async def test_async_retries_429(monkeypatch: pytest.MonkeyPatch):
    async def fast_sleep(_: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)

    responses = iter([httpx.Response(429, text="slow down"), httpx.Response(202)])
    route = respx.post("http://fake/v1/events").mock(
        side_effect=lambda _req: next(responses)
    )

    client = _make_client()
    _emit_one(client)
    await client.flush()

    assert route.call_count == 2


# ── sync (flush_sync) ────────────────────────────────────────────────────────

@respx.mock
def test_sync_succeeds_first_attempt():
    route = respx.post("http://fake/v1/events").mock(
        return_value=httpx.Response(202, json={"accepted": 1})
    )
    client = _make_client()
    _emit_one(client)
    client.flush_sync()
    assert route.call_count == 1


@respx.mock
def test_sync_retries_once_on_503_then_succeeds(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)

    responses = iter([httpx.Response(503, text="down"), httpx.Response(202)])
    route = respx.post("http://fake/v1/events").mock(
        side_effect=lambda _req: next(responses)
    )

    client = _make_client()
    _emit_one(client)
    client.flush_sync()

    assert route.call_count == 2


@respx.mock
def test_sync_exhausts_retries_and_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)

    route = respx.post("http://fake/v1/events").mock(
        return_value=httpx.Response(503, text="down")
    )

    client = _make_client()
    _emit_one(client)

    with pytest.raises(httpx.HTTPStatusError):
        client.flush_sync()

    assert route.call_count == 4


@respx.mock
def test_sync_does_not_retry_400():
    route = respx.post("http://fake/v1/events").mock(
        return_value=httpx.Response(400, text="bad")
    )

    client = _make_client()
    _emit_one(client)

    with pytest.raises(httpx.HTTPStatusError):
        client.flush_sync()

    assert route.call_count == 1
