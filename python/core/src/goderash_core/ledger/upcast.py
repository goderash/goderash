"""Schema evolution via upcasters.

When an event type changes shape, we keep every historical version intact.
At read time, older versions are transformed forward through a chain of
registered upcasters into the current shape. The raw row in Postgres is
never modified.

Register an upcaster:

    @registry.register(from_version=1, to_version=2, event_type="tool.invoked")
    def upcast(payload: dict) -> dict:
        payload["tool_category"] = "query"  # default for historical rows
        return payload
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

Upcaster = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class _UpcasterKey:
    event_type: str
    from_version: int
    to_version: int


@dataclass
class UpcasterRegistry:
    """Registry of forward migrations keyed by (event_type, from_version)."""

    _by_event: dict[tuple[str, int], Upcaster] = field(default_factory=dict)
    _current_version: dict[str, int] = field(default_factory=dict)

    def register(
        self,
        *,
        from_version: int,
        to_version: int,
        event_type: str,
    ) -> Callable[[Upcaster], Upcaster]:
        if to_version != from_version + 1:
            raise ValueError(
                f"Upcasters must step one version at a time "
                f"(got {from_version} -> {to_version})"
            )

        def decorator(fn: Upcaster) -> Upcaster:
            key = (event_type, from_version)
            if key in self._by_event:
                raise ValueError(f"Upcaster already registered for {key}")
            self._by_event[key] = fn
            self._current_version[event_type] = max(
                self._current_version.get(event_type, 0), to_version
            )
            return fn

        return decorator

    def current_version(self, event_type: str) -> int:
        return self._current_version.get(event_type, 1)

    def upcast(
        self,
        *,
        event_type: str,
        from_version: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Walk the chain from `from_version` up to the registered head."""
        if event_type not in self._current_version:
            raise LookupError(
                f"No upcasters registered for event type '{event_type}'; "
                "cannot determine current schema version."
            )
        current_version = self.current_version(event_type)
        v = from_version
        p = dict(payload)
        while v < current_version:
            fn = self._by_event.get((event_type, v))
            if fn is None:
                raise LookupError(
                    f"Missing upcaster for {event_type} v{v} -> v{v + 1}; "
                    "ledger cannot advance this row to current schema."
                )
            p = fn(p)
            v += 1
        return p


# Module-level shared registry. In tests you may construct a fresh one.
registry = UpcasterRegistry()
