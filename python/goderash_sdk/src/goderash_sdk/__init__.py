"""Goderash Python SDK.

Wrap any agent with one import:

    from goderash_sdk import GoderashClient, wrap_tool

    goderash = GoderashClient(
        api_key="gdr_...",
        tenant="my-company",
        agent_id="ops-agent-v1",
    )

    @wrap_tool(goderash, category="action", confirmation="biometric")
    def transfer_money(src, dst, amount):
        ...
"""

from .client import GoderashClient, GoderashContext
from .events import (
    AgentTurnCompleted,
    AgentTurnStarted,
    ContractViolated,
    LLMCallCompleted,
    LLMCallStarted,
    PermissionDenied,
    PermissionGranted,
    ToolCompleted,
    ToolFailed,
    ToolInvoked,
    GoderashEvent,
)
from .wrap import wrap_agent, wrap_llm, wrap_tool

__all__ = [
    "AgentTurnCompleted",
    "AgentTurnStarted",
    "ContractViolated",
    "LLMCallCompleted",
    "LLMCallStarted",
    "PermissionDenied",
    "PermissionGranted",
    "ToolCompleted",
    "ToolFailed",
    "ToolInvoked",
    "GoderashClient",
    "GoderashContext",
    "GoderashEvent",
    "wrap_agent",
    "wrap_llm",
    "wrap_tool",
]

__version__ = "0.1.0"
