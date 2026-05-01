"""LangChain/LangGraph `BaseCallbackHandler` that routes events into Goderash.

What we map:
  on_tool_start  -> tool.invoked
  on_tool_end    -> tool.completed
  on_tool_error  -> tool.failed
  on_llm_start   -> llm.call.started
  on_llm_end     -> llm.call.completed
  on_chain_start (root) -> agent.turn.started
  on_chain_end   (root) -> agent.turn.completed
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler

from goderash_sdk import GoderashClient, GoderashContext
from goderash_sdk.events import (
    AgentTurnCompleted,
    AgentTurnStarted,
    LLMCallCompleted,
    LLMCallStarted,
    ToolCompleted,
    ToolFailed,
    ToolInvoked,
)


def _hash_json(obj: Any) -> str:
    try:
        blob = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    except TypeError:
        blob = repr(obj)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class GoderashCallback(BaseCallbackHandler):
    """Convert LangChain callback events into Goderash events.

    Pass `context=` if you want to pin this callback to a specific conversation
    and turn; otherwise a new context is minted at first use.
    """

    raise_error = False
    run_inline = True

    def __init__(
        self,
        client: GoderashClient,
        *,
        context: GoderashContext | None = None,
    ) -> None:
        self._client = client
        self._ctx = context or client.new_context()
        # per-run_id bookkeeping for durations
        self._started: dict[UUID, float] = {}
        self._root_run_id: UUID | None = None

    @property
    def goderash_context(self) -> GoderashContext:
        return self._ctx

    # ---- Chain (we use the root chain as the "agent turn") ------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        if parent_run_id is None and self._root_run_id is None:
            self._root_run_id = run_id
            self._started[run_id] = time.perf_counter()
            user_message = _extract_user_message(inputs)
            self._client.emit(self._ctx, AgentTurnStarted(user_message=user_message))

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        if parent_run_id is None and run_id == self._root_run_id:
            started = self._started.pop(run_id, time.perf_counter())
            duration_ms = int((time.perf_counter() - started) * 1000)
            assistant = _extract_assistant_text(outputs)
            self._client.emit(
                self._ctx,
                AgentTurnCompleted(
                    assistant_message=assistant,
                    input_tokens=0,
                    output_tokens=0,
                    tool_calls_made=0,
                    duration_ms=duration_ms,
                    stop_reason="end_turn",
                ),
            )
            self._root_run_id = None

    # ---- Tool events --------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._started[run_id] = time.perf_counter()
        tool_name = (serialized or {}).get("name") or "unknown_tool"
        self._client.emit(
            self._ctx,
            ToolInvoked(
                tool_name=tool_name,
                tool_category="query",
                input_args_hash=_hash_json(input_str),
            ),
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started = self._started.pop(run_id, time.perf_counter())
        duration_ms = int((time.perf_counter() - started) * 1000)
        tool_name = kwargs.get("name") or "unknown_tool"
        self._client.emit(
            self._ctx,
            ToolCompleted(
                tool_name=tool_name,
                success=True,
                duration_ms=duration_ms,
                result_hash=_hash_json(output),
            ),
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started = self._started.pop(run_id, time.perf_counter())
        duration_ms = int((time.perf_counter() - started) * 1000)
        tool_name = kwargs.get("name") or "unknown_tool"
        self._client.emit(
            self._ctx,
            ToolFailed(
                tool_name=tool_name,
                error_class=type(error).__name__,
                error_message=str(error)[:1024],
                duration_ms=duration_ms,
            ),
        )

    # ---- LLM events ---------------------------------------------------

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._started[run_id] = time.perf_counter()
        model = (serialized or {}).get("id", ["", "", "", "unknown"])[-1]
        provider = _infer_provider(serialized)
        self._client.emit(
            self._ctx,
            LLMCallStarted(provider=provider, model=str(model)),
        )

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        started = self._started.pop(run_id, time.perf_counter())
        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = _extract_usage(response)
        model = getattr(response, "llm_output", None) or {}
        model_name = model.get("model_name") if isinstance(model, dict) else "unknown"
        self._client.emit(
            self._ctx,
            LLMCallCompleted(
                provider=model.get("provider", "unknown") if isinstance(model, dict) else "unknown",
                model=str(model_name),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_tokens", 0),
                cache_creation_tokens=usage.get("cache_creation_tokens", 0),
                duration_ms=duration_ms,
                stop_reason=None,
            ),
        )


def _infer_provider(serialized: dict[str, Any] | None) -> str:
    if not serialized:
        return "unknown"
    ids = serialized.get("id") or []
    if not ids:
        return "unknown"
    head = ids[-1].lower() if isinstance(ids, list) else str(ids).lower()
    if "anthropic" in head:
        return "anthropic"
    if "openai" in head:
        return "openai"
    if "google" in head or "vertex" in head:
        return "google"
    return "unknown"


def _extract_user_message(inputs: dict[str, Any]) -> str:
    # Best-effort: LangGraph states vary. Common shapes:
    # - {"messages": [HumanMessage("..."), ...]}
    # - {"input": "..."}
    # - {"query": "..."}
    if not isinstance(inputs, dict):
        return ""
    for key in ("input", "query", "message", "user_message"):
        v = inputs.get(key)
        if isinstance(v, str):
            return v
    messages = inputs.get("messages")
    if isinstance(messages, list):
        for m in messages:
            if getattr(m, "type", None) == "human":
                return str(getattr(m, "content", ""))
    return ""


def _extract_assistant_text(outputs: dict[str, Any]) -> str:
    if not isinstance(outputs, dict):
        return ""
    for key in ("output", "result", "answer"):
        v = outputs.get(key)
        if isinstance(v, str):
            return v
    messages = outputs.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        content = getattr(last, "content", "")
        if isinstance(content, str):
            return content
    return ""


def _extract_usage(response: Any) -> dict[str, int]:
    # LangChain puts usage in `response.llm_output["token_usage"]` or on
    # `generations[0][0].generation_info`. Best-effort extraction.
    if response is None:
        return {}
    llm_output = getattr(response, "llm_output", None) or {}
    usage = llm_output.get("token_usage") if isinstance(llm_output, dict) else None
    if isinstance(usage, dict):
        return {
            "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
            "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
            "cache_creation_tokens": int(usage.get("cache_creation_input_tokens") or 0),
        }
    return {}
