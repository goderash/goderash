"""Wrap an `anthropic.Anthropic` client and read tool_use blocks from responses."""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

from goderash_sdk import GoderashClient, GoderashContext
from goderash_sdk.events import LLMCallCompleted, LLMCallStarted, ToolInvoked

if TYPE_CHECKING:  # pragma: no cover
    from anthropic import Anthropic  # type: ignore[import-not-found]


def _hash(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def wrap_anthropic(
    anthropic_client: Anthropic,
    *,
    goderash: GoderashClient,
    context: GoderashContext,
    provider: str = "anthropic",
) -> Anthropic:
    """Replace `messages.create` with an audited proxy. Original method stays
    accessible as `messages._goderash_orig_create`.
    """
    target = anthropic_client.messages
    original = target.create
    setattr(target, "_goderash_orig_create", original)

    def proxy(*args: Any, **kwargs: Any) -> Any:
        model = str(kwargs.get("model") or "unknown")
        started = time.perf_counter()
        goderash.emit(context, LLMCallStarted(provider=provider, model=model))
        result = original(*args, **kwargs)
        duration_ms = int((time.perf_counter() - started) * 1000)
        audit_messages_response(goderash, context, result, provider=provider, model=model,
                                duration_ms=duration_ms)
        return result

    target.create = proxy  # type: ignore[method-assign]
    return anthropic_client


def audit_messages_response(
    goderash: GoderashClient,
    context: GoderashContext,
    response: Any,
    *,
    provider: str = "anthropic",
    model: str | None = None,
    duration_ms: int = 0,
) -> None:
    """Emit one `llm.call.completed` plus a `tool.invoked` per tool_use block.

    The `tool_use` blocks the model emits are *requests* — Goderash treats them
    as `tool.invoked` events. Your application code is responsible for the
    matching `tool.completed` / `tool.failed` after running the tool.
    """
    usage = getattr(response, "usage", None)
    if hasattr(usage, "model_dump"):
        usage_dict = usage.model_dump()
    elif isinstance(usage, dict):
        usage_dict = usage
    else:
        usage_dict = {}

    goderash.emit(
        context,
        LLMCallCompleted(
            provider=provider,
            model=str(model or getattr(response, "model", "unknown")),
            input_tokens=int(usage_dict.get("input_tokens") or 0),
            output_tokens=int(usage_dict.get("output_tokens") or 0),
            cache_read_tokens=int(usage_dict.get("cache_read_input_tokens") or 0),
            cache_creation_tokens=int(usage_dict.get("cache_creation_input_tokens") or 0),
            duration_ms=duration_ms,
            stop_reason=getattr(response, "stop_reason", None),
        ),
    )

    content_blocks = getattr(response, "content", []) or []
    for block in content_blocks:
        block_type = getattr(block, "type", None)
        if block_type == "tool_use":
            goderash.emit(
                context,
                ToolInvoked(
                    tool_name=str(getattr(block, "name", "unknown")),
                    tool_category="query",
                    input_args_hash=_hash(getattr(block, "input", {})),
                ),
            )
