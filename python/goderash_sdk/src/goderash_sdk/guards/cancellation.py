"""Cooperative cancellation token.

`/stop`, a WS disconnect, or any operator action calls `cancel()`. Long-
running tools should call `token.raise_if_cancelled()` between steps so the
agent can wind down gracefully.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


class CancelledError(RuntimeError):
    """Raised when a tool checks the token after cancellation."""


@dataclass
class CancellationToken:
    _event: threading.Event = field(default_factory=threading.Event)
    reason: str | None = None

    def cancel(self, reason: str | None = None) -> None:
        self.reason = reason
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise CancelledError(self.reason or "cancelled")
