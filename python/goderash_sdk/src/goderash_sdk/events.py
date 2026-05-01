"""Event types — a mirror of the ledger's canonical schema.

We redeclare the types in the SDK to avoid a hard import dependency on the
control-plane package. The wire format is identical.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class _EventBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AgentTurnStarted(_EventBase):
    event_type: Literal["agent.turn.started"] = "agent.turn.started"
    user_message: str
    language: str | None = None
    input_tokens_budget: int | None = None
    tool_budget: int | None = None


class AgentTurnCompleted(_EventBase):
    event_type: Literal["agent.turn.completed"] = "agent.turn.completed"
    assistant_message: str
    input_tokens: int
    output_tokens: int
    tool_calls_made: int
    duration_ms: int
    stop_reason: Literal["end_turn", "max_tokens", "tool_use", "stopped", "error"]


class ToolInvoked(_EventBase):
    event_type: Literal["tool.invoked"] = "tool.invoked"
    tool_name: str
    tool_category: Literal["query", "action", "intelligence"]
    input_args_hash: str
    input_args_preview: dict[str, Any] | None = None
    confirmation_type: Literal["none", "pin", "biometric", "otp"] = "none"


class ToolCompleted(_EventBase):
    event_type: Literal["tool.completed"] = "tool.completed"
    tool_name: str
    success: bool
    duration_ms: int
    result_hash: str
    result_preview: dict[str, Any] | None = None


class ToolFailed(_EventBase):
    event_type: Literal["tool.failed"] = "tool.failed"
    tool_name: str
    error_class: str
    error_message: str
    duration_ms: int


class LLMCallStarted(_EventBase):
    event_type: Literal["llm.call.started"] = "llm.call.started"
    provider: str
    model: str
    input_tokens_estimated: int | None = None
    tools_offered: list[str] = Field(default_factory=list)


class LLMCallCompleted(_EventBase):
    event_type: Literal["llm.call.completed"] = "llm.call.completed"
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    duration_ms: int
    stop_reason: str | None = None


class PermissionGranted(_EventBase):
    event_type: Literal["permission.granted"] = "permission.granted"
    tool_name: str
    source: Literal["rule", "user", "hook", "classifier", "bypass"]
    reason: str | None = None


class PermissionDenied(_EventBase):
    event_type: Literal["permission.denied"] = "permission.denied"
    tool_name: str
    source: Literal["rule", "user", "hook", "classifier", "fraud_guard", "velocity", "budget"]
    reason: str


class ContractViolated(_EventBase):
    event_type: Literal["contract.violated"] = "contract.violated"
    contract_id: str
    contract_version: str
    clause: str
    severity: Literal["info", "warn", "error", "critical"]
    details: dict[str, Any] = Field(default_factory=dict)
    blame_chain: list[str] = Field(default_factory=list)


GoderashEventPayload = Annotated[
    (
        AgentTurnStarted
        | AgentTurnCompleted
        | ToolInvoked
        | ToolCompleted
        | ToolFailed
        | LLMCallStarted
        | LLMCallCompleted
        | PermissionGranted
        | PermissionDenied
        | ContractViolated
    ),
    Field(discriminator="event_type"),
]


class GoderashEvent(BaseModel):
    """Envelope sent to the control plane."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    agent_id: str
    conversation_id: str
    turn_id: str
    parent_event_id: UUID | None = None
    schema_version: int = 1
    occurred_at: datetime = Field(default_factory=_utcnow)
    payload: GoderashEventPayload
