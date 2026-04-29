"""Runtime guards lifted from production banking-grade patterns.

These run **inside** the agent process (or in a sidecar). Each guard returns
a `GuardDecision` and emits an audit event into the Goderash ledger. They are
composable: order them in a list, run sequentially, short-circuit on the
first deny.

Composition example::

    guards = GuardChain(
        FraudGuard(),
        PermissionModeGate(mode=PermissionMode.DEFAULT),
        VelocityLimiter(redis_url="redis://localhost"),
        ConversationBudget(max_tool_calls=20, max_tokens=200_000),
    )
    decision = guards.evaluate(client, ctx, tool_name="transfer_money", amount=500)
    if decision.allow:
        run_tool(...)
"""

from .budget import ConversationBudget, ConversationBudgetState
from .cancellation import CancellationToken
from .chain import GuardChain, GuardDecision, GuardError
from .fraud import FraudGuard, FraudVerdict
from .permission_mode import PermissionMode, PermissionModeGate
from .velocity import VelocityCounter, VelocityLimiter, VelocityRule

__all__ = [
    "CancellationToken",
    "ConversationBudget",
    "ConversationBudgetState",
    "FraudGuard",
    "FraudVerdict",
    "GuardChain",
    "GuardDecision",
    "GuardError",
    "PermissionMode",
    "PermissionModeGate",
    "VelocityCounter",
    "VelocityLimiter",
    "VelocityRule",
]
