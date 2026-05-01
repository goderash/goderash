"""Per-conversation budgets — hard caps enforced at the tool boundary.

Tracks tokens and tool-call counts. Exhaustion denies the next call only;
prior work is preserved in the ledger.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..client import GoderashClient, GoderashContext
from .chain import GuardDecision


@dataclass
class ConversationBudgetState:
    tokens_used: int = 0
    tool_calls_used: int = 0


@dataclass
class ConversationBudget:
    max_tool_calls: int | None = None
    max_tokens: int | None = None

    _state_by_conv: dict[str, ConversationBudgetState] = field(
        default_factory=lambda: defaultdict(ConversationBudgetState)
    )
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def consume_tokens(self, conversation_id: str, tokens: int) -> None:
        with self._lock:
            self._state_by_conv[conversation_id].tokens_used += int(tokens)

    def state(self, conversation_id: str) -> ConversationBudgetState:
        with self._lock:
            return self._state_by_conv[conversation_id]

    def reset(self, conversation_id: str) -> None:
        with self._lock:
            self._state_by_conv.pop(conversation_id, None)

    def evaluate(
        self,
        client: GoderashClient,
        ctx: GoderashContext,
        *,
        tool_name: str,
        **_: Any,
    ) -> GuardDecision:
        with self._lock:
            state = self._state_by_conv[ctx.conversation_id]

            if self.max_tool_calls is not None and state.tool_calls_used >= self.max_tool_calls:
                return GuardDecision.deny(
                    "budget",
                    f"tool-call budget exhausted ({state.tool_calls_used}/{self.max_tool_calls})",
                )
            if self.max_tokens is not None and state.tokens_used >= self.max_tokens:
                return GuardDecision.deny(
                    "budget",
                    f"token budget exhausted ({state.tokens_used}/{self.max_tokens})",
                )

            # Record the attempt up-front so concurrent calls under the same
            # conversation are bounded.
            state.tool_calls_used += 1
        return GuardDecision.grant("rule", "budget ok")
