"""`@wrap_llm` — audits LLM calls.

Emits `llm.call.started` + `llm.call.completed`. The wrapped function must
return an object exposing `input_tokens`, `output_tokens`, and optionally
`stop_reason`. If the return shape is different, pass a `token_extractor`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from ..client import GoderashClient, GoderashContext
from ..events import LLMCallCompleted, LLMCallStarted

F = TypeVar("F", bound=Callable[..., Any])


def _default_extract_tokens(result: Any) -> tuple[int, int, int, int, str | None]:
    """Extract (input, output, cache_read, cache_creation, stop_reason)."""
    inp = getattr(result, "input_tokens", 0) or 0
    out = getattr(result, "output_tokens", 0) or 0
    cache_r = getattr(result, "cache_read_tokens", 0) or 0
    cache_c = getattr(result, "cache_creation_tokens", 0) or 0
    stop = getattr(result, "stop_reason", None)
    if isinstance(result, dict):
        inp = result.get("input_tokens", inp)
        out = result.get("output_tokens", out)
        cache_r = result.get("cache_read_tokens", cache_r)
        cache_c = result.get("cache_creation_tokens", cache_c)
        stop = result.get("stop_reason", stop)
    return int(inp), int(out), int(cache_r), int(cache_c), stop


def wrap_llm(
    client: GoderashClient,
    *,
    provider: str,
    model: str,
    context: GoderashContext | None = None,
    token_extractor: Callable[[Any], tuple[int, int, int, int, str | None]] | None = None,
) -> Callable[[F], F]:
    extractor = token_extractor or _default_extract_tokens

    def decorator(fn: F) -> F:
        if asyncio.iscoroutinefunction(fn):

            @wraps(fn)
            async def awrapped(*args: Any, **kwargs: Any) -> Any:
                ctx = kwargs.pop("_goderash_context", None) or context
                if ctx is None:
                    return await fn(*args, **kwargs)

                started_at = time.perf_counter()
                client.emit(ctx, LLMCallStarted(provider=provider, model=model))
                result = await fn(*args, **kwargs)
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                inp, out, cr, cc, stop = extractor(result)
                client.emit(
                    ctx,
                    LLMCallCompleted(
                        provider=provider,
                        model=model,
                        input_tokens=inp,
                        output_tokens=out,
                        cache_read_tokens=cr,
                        cache_creation_tokens=cc,
                        duration_ms=duration_ms,
                        stop_reason=stop,
                    ),
                )
                return result

            return awrapped  # type: ignore[return-value]

        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            ctx = kwargs.pop("_goderash_context", None) or context
            if ctx is None:
                return fn(*args, **kwargs)

            started_at = time.perf_counter()
            client.emit(ctx, LLMCallStarted(provider=provider, model=model))
            result = fn(*args, **kwargs)
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            inp, out, cr, cc, stop = extractor(result)
            client.emit(
                ctx,
                LLMCallCompleted(
                    provider=provider,
                    model=model,
                    input_tokens=inp,
                    output_tokens=out,
                    cache_read_tokens=cr,
                    cache_creation_tokens=cc,
                    duration_ms=duration_ms,
                    stop_reason=stop,
                ),
            )
            return result

        return wrapped  # type: ignore[return-value]

    return decorator
