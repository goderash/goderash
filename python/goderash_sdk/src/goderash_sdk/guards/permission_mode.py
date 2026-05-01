"""Permission mode gate.

Modes (matching Claude Code + Dashen AIR semantics):

| Mode    | Behavior                                                |
|---------|---------------------------------------------------------|
| PLAN    | All actions are denied (dry-run); reads allowed.        |
| DEFAULT | Actions require explicit confirmation; reads auto-ok.   |
| AUTO    | All allowed by rule; explicit denies only.              |
| STRICT  | Confirm everything, including reads.                    |

The gate consults a callable `confirm_callback(tool_name, **kwargs) -> bool`
when a mode requires confirmation. Pass an explicit callback during testing.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from ..client import GoderashClient, GoderashContext
from .chain import GuardDecision

ToolCategory = Literal["query", "action", "intelligence"]


class PermissionMode(str, enum.Enum):
    PLAN = "plan"
    DEFAULT = "default"
    AUTO = "auto"
    STRICT = "strict"


ConfirmCallback = Callable[..., bool]


@dataclass
class PermissionModeGate:
    mode: PermissionMode = PermissionMode.DEFAULT
    confirm: ConfirmCallback | None = None
    """If set, called when a mode requires explicit confirmation."""

    def evaluate(
        self,
        client: GoderashClient,
        ctx: GoderashContext,
        *,
        tool_name: str,
        category: ToolCategory = "query",
        **kwargs: Any,
    ) -> GuardDecision:
        if self.mode == PermissionMode.PLAN:
            if category == "action":
                return GuardDecision.deny(
                    "rule", "PLAN mode: action tools are dry-run only"
                )
            return GuardDecision.grant("rule", reason="PLAN mode: read allowed")

        if self.mode == PermissionMode.AUTO:
            return GuardDecision.grant("rule", reason="AUTO mode")

        if self.mode == PermissionMode.STRICT:
            if not self._ask("strict", tool_name, **kwargs):
                return GuardDecision.deny("user", "STRICT mode: user declined confirmation")
            return GuardDecision.grant("user", reason="STRICT mode: user confirmed")

        # DEFAULT
        if category == "action":
            if not self._ask("default", tool_name, **kwargs):
                return GuardDecision.deny("user", "DEFAULT mode: user declined confirmation")
            return GuardDecision.grant("user", reason="DEFAULT mode: user confirmed action")
        return GuardDecision.grant("rule", reason="DEFAULT mode: read auto-allowed")

    def _ask(self, mode: str, tool_name: str, **kwargs: Any) -> bool:
        if self.confirm is None:
            # Fail safe: without a callback wired up, deny.
            return False
        try:
            return bool(self.confirm(tool_name=tool_name, mode=mode, **kwargs))
        except Exception:
            return False
