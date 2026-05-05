"""GoderashClient — the one object callers instantiate.

Responsibilities:
- Hold auth + tenant + agent identity.
- Buffer events and flush in batches to the control plane.
- Surface a request-scoped `GoderashContext` that carries conversation + turn IDs.

The client is safe to share across threads/tasks. Every method is idempotent
on failure (retries; duplicate events are deduped server-side by `event_id`).
"""

from __future__ import annotations

import asyncio
import os
import random
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import httpx
import structlog

from .events import GoderashEvent

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

log = structlog.get_logger()

_RETRY_MAX: int = 3
_RETRY_BASE: float = 0.5
_RETRY_CAP: float = 10.0
_RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def _jitter_delay(attempt: int) -> float:
    """Full-jitter exponential backoff. Returns seconds to sleep before the next attempt."""
    ceiling = min(_RETRY_BASE * (2 ** attempt), _RETRY_CAP)
    return random.uniform(0.0, ceiling)


@dataclass
class GoderashContext:
    """Request-scoped identity. Passed to every wrapper."""

    tenant_id: str
    agent_id: str
    conversation_id: str
    turn_id: str
    parent_event_id: UUID | None = None


@dataclass
class _ClientState:
    buffer: list[GoderashEvent] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


class GoderashClient:
    """Primary entry point for emitting events to Goderash."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        tenant: str | None = None,
        agent_id: str | None = None,
        endpoint: str | None = None,
        batch_size: int = 50,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("GODERASH_API_KEY") or ""
        self.tenant = tenant or os.environ.get("GODERASH_TENANT") or ""
        self.agent_id = agent_id or os.environ.get("GODERASH_AGENT_ID") or "default"
        self.endpoint = (
            endpoint or os.environ.get("GODERASH_ENDPOINT") or "http://localhost:8000"
        ).rstrip("/")
        self.batch_size = batch_size
        self.timeout_seconds = timeout_seconds

        if not self.api_key:
            raise ValueError("GoderashClient requires api_key (or GODERASH_API_KEY env var)")
        if not self.tenant:
            raise ValueError("GoderashClient requires tenant (or GODERASH_TENANT env var)")

        self._state = _ClientState()
        self._http: httpx.AsyncClient | None = None

    # ---- context helpers ------------------------------------------------

    def new_context(
        self,
        *,
        conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> GoderashContext:
        return GoderashContext(
            tenant_id=self.tenant,
            agent_id=self.agent_id,
            conversation_id=conversation_id or str(uuid4()),
            turn_id=turn_id or str(uuid4()),
        )

    @contextmanager
    def turn(
        self,
        *,
        conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> Iterator[GoderashContext]:
        ctx = self.new_context(conversation_id=conversation_id, turn_id=turn_id)
        yield ctx
        try:
            self.flush_sync()
        except Exception as e:
            log.warning("goderash.flush.failed", error=str(e))

    @asynccontextmanager
    async def async_turn(
        self,
        *,
        conversation_id: str | None = None,
        turn_id: str | None = None,
    ) -> AsyncIterator[GoderashContext]:
        ctx = self.new_context(conversation_id=conversation_id, turn_id=turn_id)
        try:
            yield ctx
        finally:
            try:
                await self.flush()
            except Exception as e:
                log.warning("goderash.flush.failed", error=str(e))

    # ---- emission -------------------------------------------------------

    def emit(self, ctx: GoderashContext, payload: object) -> None:
        """Buffer an event. Non-blocking. Flushes when batch is full."""
        event = GoderashEvent(
            tenant_id=ctx.tenant_id,
            agent_id=ctx.agent_id,
            conversation_id=ctx.conversation_id,
            turn_id=ctx.turn_id,
            parent_event_id=ctx.parent_event_id,
            payload=payload,  # type: ignore[arg-type]
        )
        with self._state.lock:
            self._state.buffer.append(event)
            should_flush = len(self._state.buffer) >= self.batch_size

        if should_flush:
            self.flush_sync()

    # ---- flushing -------------------------------------------------------

    def flush_sync(self) -> None:
        """Blocking flush — safe from sync code."""
        batch = self._drain()
        if not batch:
            return
        with httpx.Client(timeout=self.timeout_seconds) as client:
            self._post(client, batch)

    async def flush(self) -> None:
        """Async flush."""
        batch = self._drain()
        if not batch:
            return
        client = await self._async_client()
        await self._post_async(client, batch)

    async def aclose(self) -> None:
        await self.flush()
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ---- internals ------------------------------------------------------

    def _drain(self) -> list[GoderashEvent]:
        with self._state.lock:
            batch = self._state.buffer[:]
            self._state.buffer.clear()
        return batch

    def _headers(self) -> dict[str, str]:
        return {
            "X-Goderash-Api-Key": self.api_key,
            "X-Goderash-Tenant": self.tenant,
            "Content-Type": "application/json",
        }

    def _post(self, client: httpx.Client, batch: list[GoderashEvent]) -> None:
        payload = {"events": [e.model_dump(mode="json") for e in batch]}
        last_exc: Exception | None = None

        for attempt in range(_RETRY_MAX + 1):
            try:
                r = client.post(
                    f"{self.endpoint}/v1/events",
                    headers=self._headers(),
                    json=payload,
                )
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                log.warning("goderash.ingest.retrying", attempt=attempt, error=str(exc))
            else:
                if r.status_code < 400:
                    return
                log.error("goderash.ingest.failed", status=r.status_code, body=r.text[:500])
                if r.status_code not in _RETRYABLE_STATUSES:
                    r.raise_for_status()
                last_exc = httpx.HTTPStatusError(
                    f"goderash ingest {r.status_code}",
                    request=r.request,
                    response=r,
                )
                log.warning("goderash.ingest.retrying", attempt=attempt, status=r.status_code)

            if attempt < _RETRY_MAX:
                time.sleep(_jitter_delay(attempt))

        assert last_exc is not None
        raise last_exc

    async def _post_async(self, client: httpx.AsyncClient, batch: list[GoderashEvent]) -> None:
        payload = {"events": [e.model_dump(mode="json") for e in batch]}
        last_exc: Exception | None = None

        for attempt in range(_RETRY_MAX + 1):
            try:
                r = await client.post(
                    f"{self.endpoint}/v1/events",
                    headers=self._headers(),
                    json=payload,
                )
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                log.warning("goderash.ingest.retrying", attempt=attempt, error=str(exc))
            else:
                if r.status_code < 400:
                    return
                log.error("goderash.ingest.failed", status=r.status_code, body=r.text[:500])
                if r.status_code not in _RETRYABLE_STATUSES:
                    r.raise_for_status()
                last_exc = httpx.HTTPStatusError(
                    f"goderash ingest {r.status_code}",
                    request=r.request,
                    response=r,
                )
                log.warning("goderash.ingest.retrying", attempt=attempt, status=r.status_code)

            if attempt < _RETRY_MAX:
                await asyncio.sleep(_jitter_delay(attempt))

        assert last_exc is not None
        raise last_exc

    async def _async_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._http

    # Safety net for sync callers who forgot to flush.
    def __del__(self) -> None:  # pragma: no cover
        try:
            if self._state.buffer:
                self.flush_sync()
        except Exception:
            pass
        if self._http is not None:
            try:
                asyncio.get_event_loop().run_until_complete(self._http.aclose())
            except Exception:
                pass
