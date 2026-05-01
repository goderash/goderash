"""Velocity limiter — sliding window counters per (tenant, user, tool).

Two backends:

- **In-memory** (default for tests / single-process): a dict of bounded deques.
- **Redis** (production): atomic INCR with a TTL window.

Rules are a tuple of `(window_seconds, max_count, max_amount)`. Any rule's
violation denies the call.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..client import GoderashClient, GoderashContext
from .chain import GuardDecision


@dataclass(frozen=True)
class VelocityRule:
    window_seconds: int
    max_count: int | None = None
    max_amount: float | None = None
    label: str = ""


class VelocityCounter(Protocol):
    def record(self, key: str, *, amount: float | None, now: float) -> None: ...
    def count_in_window(self, key: str, window_seconds: int, now: float) -> int: ...
    def amount_in_window(self, key: str, window_seconds: int, now: float) -> float: ...


@dataclass
class InMemoryVelocityCounter:
    """Thread-safe in-memory sliding window. Suitable for tests/single-proc."""

    _events: dict[str, deque[tuple[float, float]]] = field(
        default_factory=lambda: defaultdict(deque)
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, key: str, *, amount: float | None, now: float) -> None:
        with self._lock:
            self._events[key].append((now, float(amount or 0.0)))

    def _trim(self, key: str, oldest: float) -> None:
        d = self._events.get(key)
        if d is None:
            return
        while d and d[0][0] < oldest:
            d.popleft()

    def count_in_window(self, key: str, window_seconds: int, now: float) -> int:
        oldest = now - window_seconds
        with self._lock:
            self._trim(key, oldest)
            return len(self._events.get(key, ()))

    def amount_in_window(self, key: str, window_seconds: int, now: float) -> float:
        oldest = now - window_seconds
        with self._lock:
            self._trim(key, oldest)
            return float(sum(a for _, a in self._events.get(key, ())))


@dataclass
class RedisVelocityCounter:
    """Atomic Redis-backed counter using sorted sets keyed by timestamp."""

    redis: Any  # redis.Redis instance — typed loosely to avoid hard dep.
    namespace: str = "goderash:velocity"

    def _zkey(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def record(self, key: str, *, amount: float | None, now: float) -> None:
        # Member is a unique string per event; score is `now`. We store
        # the amount as the member suffix so we can sum it when needed.
        member = f"{now:.6f}:{amount or 0.0}"
        pipe = self.redis.pipeline()
        pipe.zadd(self._zkey(key), {member: now})
        # Keep one day of history at most; rules narrower than that read directly.
        pipe.zremrangebyscore(self._zkey(key), 0, now - 86_400)
        pipe.expire(self._zkey(key), 86_400)
        pipe.execute()

    def count_in_window(self, key: str, window_seconds: int, now: float) -> int:
        return int(self.redis.zcount(self._zkey(key), now - window_seconds, now))

    def amount_in_window(self, key: str, window_seconds: int, now: float) -> float:
        members = self.redis.zrangebyscore(self._zkey(key), now - window_seconds, now)
        total = 0.0
        for raw in members:
            m = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            try:
                _, amt = m.split(":", 1)
                total += float(amt)
            except ValueError:
                continue
        return total


@dataclass
class VelocityLimiter:
    rules_by_tool: dict[str, list[VelocityRule]] = field(default_factory=dict)
    counter: VelocityCounter = field(default_factory=InMemoryVelocityCounter)
    user_id_kwarg: str = "user_id"
    amount_kwarg: str = "amount"

    def evaluate(
        self,
        client: GoderashClient,
        ctx: GoderashContext,
        *,
        tool_name: str,
        **kwargs: Any,
    ) -> GuardDecision:
        rules = self.rules_by_tool.get(tool_name, [])
        if not rules:
            return GuardDecision.grant("rule", "no velocity rule")

        user_id = kwargs.get(self.user_id_kwarg) or "anonymous"
        amount = kwargs.get(self.amount_kwarg)
        key = f"{ctx.tenant_id}:{user_id}:{tool_name}"
        now = time.time()

        # Evaluate all rules; if any blocks, return deny without recording.
        for rule in rules:
            if rule.max_count is not None:
                count = self.counter.count_in_window(key, rule.window_seconds, now)
                if count >= rule.max_count:
                    return GuardDecision.deny(
                        "velocity",
                        f"velocity:{rule.label or 'count'} "
                        f"({count}/{rule.max_count} in {rule.window_seconds}s)",
                        details={
                            "rule": rule.label,
                            "window_seconds": rule.window_seconds,
                            "limit": rule.max_count,
                            "observed": count,
                        },
                    )
            if rule.max_amount is not None:
                total = self.counter.amount_in_window(key, rule.window_seconds, now)
                projected = total + float(amount or 0.0)
                if projected > rule.max_amount:
                    return GuardDecision.deny(
                        "velocity",
                        f"velocity:{rule.label or 'amount'} "
                        f"({projected:.2f}/{rule.max_amount:.2f} in {rule.window_seconds}s)",
                        details={
                            "rule": rule.label,
                            "window_seconds": rule.window_seconds,
                            "limit": rule.max_amount,
                            "projected": projected,
                        },
                    )

        # Record this attempt — guard chain only counts attempts that pass.
        self.counter.record(key, amount=amount, now=now)
        return GuardDecision.grant("rule", "velocity ok")
