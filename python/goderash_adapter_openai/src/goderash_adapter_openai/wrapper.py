"""Wrap an `openai.OpenAI` client so its calls land in the Goderash ledger."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from goderash_sdk import GoderashClient, GoderashContext
from goderash_sdk.events import LLMCallCompleted, LLMCallStarted

if TYPE_CHECKING:  # pragma: no cover
    from openai import OpenAI  # type: ignore[import-not-found]


def wrap_openai(
    openai_client: OpenAI,
    *,
    goderash: GoderashClient,
    context: GoderashContext,
    provider: str = "openai",
) -> OpenAI:
    """Return the same client; all `chat.completions.create` calls are audited.

    We intercept by replacing `chat.completions.create` and `responses.create`
    with thin proxies. The original methods stay accessible via `_goderash_orig_*`.
    """
    _wrap_method(
        openai_client,
        path=("chat", "completions"),
        attr="create",
        goderash=goderash,
        context=context,
        provider=provider,
        model_kwarg="model",
    )
    if hasattr(openai_client, "responses"):
        _wrap_method(
            openai_client,
            path=("responses",),
            attr="create",
            goderash=goderash,
            context=context,
            provider=provider,
            model_kwarg="model",
        )
    return openai_client


def _wrap_method(
    obj: Any,
    *,
    path: tuple[str, ...],
    attr: str,
    goderash: GoderashClient,
    context: GoderashContext,
    provider: str,
    model_kwarg: str,
) -> None:
    target = obj
    for p in path:
        target = getattr(target, p)

    original = getattr(target, attr)
    setattr(target, f"_goderash_orig_{attr}", original)

    def proxy(*args: Any, **kwargs: Any) -> Any:
        model = str(kwargs.get(model_kwarg) or "unknown")
        started = time.perf_counter()
        goderash.emit(context, LLMCallStarted(provider=provider, model=model))
        result = original(*args, **kwargs)
        duration_ms = int((time.perf_counter() - started) * 1000)
        usage = _extract_usage(result)
        goderash.emit(
            context,
            LLMCallCompleted(
                provider=provider,
                model=model,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cache_read_tokens=usage["cache_read_tokens"],
                cache_creation_tokens=usage["cache_creation_tokens"],
                duration_ms=duration_ms,
                stop_reason=getattr(result, "stop_reason", None)
                or _first_choice_finish_reason(result),
            ),
        )
        return result

    setattr(target, attr, proxy)


def _extract_usage(result: Any) -> dict[str, int]:
    usage = getattr(result, "usage", None) or {}
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        usage = {}
    return {
        "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        "cache_read_tokens": int(usage.get("cache_read_input_tokens") or 0),
        "cache_creation_tokens": int(usage.get("cache_creation_input_tokens") or 0),
    }


def _first_choice_finish_reason(result: Any) -> str | None:
    choices = getattr(result, "choices", None)
    if not choices:
        return None
    first = choices[0]
    return getattr(first, "finish_reason", None)
