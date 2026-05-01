"""Generic guard chain plumbing.

A guard is anything with a `.evaluate(client, ctx, **kwargs) -> GuardDecision`.
The chain runs them in order, short-circuits on the first deny, and emits
the appropriate `permission.granted` / `permission.denied` event.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

from ..client import GoderashClient, GoderashContext
from ..events import PermissionDenied, PermissionGranted

DenyReason = Literal[
    "rule",
    "user",
    "hook",
    "classifier",
    "fraud_guard",
    "velocity",
    "budget",
]


class GuardError(Exception):
    """Raised when a guard misconfigures or hits a fatal condition."""


@dataclass(frozen=True)
class GuardDecision:
    allow: bool
    source: DenyReason | Literal["bypass", "rule", "user", "hook", "classifier"]
    reason: str | None = None
    details: dict[str, Any] | None = None

    @classmethod
    def grant(
        cls,
        source: Literal["rule", "user", "hook", "classifier", "bypass"] = "rule",
        reason: str | None = None,
    ) -> GuardDecision:
        return cls(allow=True, source=source, reason=reason)

    @classmethod
    def deny(
        cls,
        source: DenyReason,
        reason: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> GuardDecision:
        return cls(allow=False, source=source, reason=reason, details=details)


@runtime_checkable
class Guard(Protocol):
    def evaluate(
        self,
        client: GoderashClient,
        ctx: GoderashContext,
        *,
        tool_name: str,
        **kwargs: Any,
    ) -> GuardDecision: ...


class GuardChain:
    """Compose guards. Order matters — run cheap deterministic checks first."""

    def __init__(self, *guards: Guard) -> None:
        self._guards: tuple[Guard, ...] = guards

    def evaluate(
        self,
        client: GoderashClient,
        ctx: GoderashContext,
        *,
        tool_name: str,
        emit: bool = True,
        **kwargs: Any,
    ) -> GuardDecision:
        for guard in self._guards:
            decision = guard.evaluate(client, ctx, tool_name=tool_name, **kwargs)
            if not decision.allow:
                if emit:
                    client.emit(
                        ctx,
                        PermissionDenied(
                            tool_name=tool_name,
                            source=decision.source,  # type: ignore[arg-type]
                            reason=decision.reason or "denied",
                        ),
                    )
                return decision

        decision = GuardDecision.grant()
        if emit:
            client.emit(
                ctx,
                PermissionGranted(
                    tool_name=tool_name,
                    source="rule",
                    reason="all guards passed",
                ),
            )
        return decision
