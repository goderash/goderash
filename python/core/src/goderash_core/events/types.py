"""Canonical event types.

Every event is an immutable Pydantic v2 model with a discriminated `event_type`.
Adding a new type: append the class here, add it to `GoderashEvent`, add a round-trip
test, bump the SCHEMA_VERSION on the parent envelope.

Breaking a type: keep the old version, add `_v2` suffix to the new one, and
register an upcaster in `ledger/upcast.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class _EventBase(BaseModel):
    """Base — frozen, strict, JSON-safe."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------
# Agent turn (a full user-input → assistant-response cycle)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tool call lifecycle
# ---------------------------------------------------------------------------


class ToolInvoked(_EventBase):
    event_type: Literal["tool.invoked"] = "tool.invoked"
    tool_name: str
    tool_category: Literal["query", "action", "intelligence"]
    input_args_hash: str  # never the raw args
    input_args_preview: dict[str, Any] | None = None  # optional, redacted
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
    error_message: str  # sanitized
    duration_ms: int


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Permission decisions (what Dashen AIR emits at the tool boundary)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Data contract violations
# ---------------------------------------------------------------------------


class ContractViolated(_EventBase):
    event_type: Literal["contract.violated"] = "contract.violated"
    contract_id: str
    contract_version: str
    clause: str
    severity: Literal["info", "warn", "error", "critical"]
    details: dict[str, Any] = Field(default_factory=dict)
    blame_chain: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------


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


SCHEMA_VERSION = 1


class GoderashEventEnvelope(BaseModel):
    """What the SDK sends and the ledger stores.

    The envelope carries provenance + chain metadata; `payload` is the typed event.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    tenant_id: str
    agent_id: str
    conversation_id: str
    turn_id: str
    parent_event_id: UUID | None = None
    schema_version: int = SCHEMA_VERSION
    occurred_at: datetime = Field(default_factory=_utcnow)
    recorded_at: datetime | None = None  # set by ledger
    payload: GoderashEventPayload
    # Hash-chain fields populated by the ledger on append (not by the SDK):
    prev_hash: str | None = None
    hash: str | None = None


# Backwards-compat alias so SDK consumers can `from goderash_sdk import GoderashEvent`
GoderashEvent = GoderashEventEnvelope
