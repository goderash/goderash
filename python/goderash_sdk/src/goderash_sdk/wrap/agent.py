"""`@wrap_agent` — brackets a full user-turn with start/completed events.

Typical use:

    @wrap_agent(goderash)
    def run_turn(user_message: str, *, _goderash_context: GoderashContext) -> str:
        ...            # orchestrate tools + llm inside
        return "final assistant text"
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, Literal, TypeVar

from ..client import GoderashClient, GoderashContext
from ..events import AgentTurnCompleted, AgentTurnStarted

F = TypeVar("F", bound=Callable[..., Any])
StopReason = Literal["end_turn", "max_tokens", "tool_use", "stopped", "error"]


def wrap_agent(
    client: GoderashClient,
    *,
    context: GoderashContext | None = None,
    language: str | None = None,
) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        if asyncio.iscoroutinefunction(fn):

            @wraps(fn)
            async def awrapped(user_message: str, *args: Any, **kwargs: Any) -> Any:
                ctx = kwargs.pop("_goderash_context", None) or context or client.new_context()
                kwargs["_goderash_context"] = ctx

                started_at = time.perf_counter()
                client.emit(
                    ctx,
                    AgentTurnStarted(user_message=user_message, language=language),
                )
                stop_reason: StopReason = "end_turn"
                try:
                    result = await fn(user_message, *args, **kwargs)
                except Exception:
                    stop_reason = "error"
                    raise
                finally:
                    duration_ms = int((time.perf_counter() - started_at) * 1000)
                    assistant_text = result if isinstance(result, str) else ""
                    client.emit(
                        ctx,
                        AgentTurnCompleted(
                            assistant_message=assistant_text,
                            input_tokens=0,
                            output_tokens=0,
                            tool_calls_made=0,
                            duration_ms=duration_ms,
                            stop_reason=stop_reason,
                        ),
                    )
                return result

            return awrapped  # type: ignore[return-value]

        @wraps(fn)
        def wrapped(user_message: str, *args: Any, **kwargs: Any) -> Any:
            ctx = kwargs.pop("_goderash_context", None) or context or client.new_context()
            kwargs["_goderash_context"] = ctx

            started_at = time.perf_counter()
            client.emit(ctx, AgentTurnStarted(user_message=user_message, language=language))
            stop_reason: StopReason = "end_turn"
            try:
                result = fn(user_message, *args, **kwargs)
            except Exception:
                stop_reason = "error"
                raise
            finally:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                assistant_text = result if isinstance(result, str) else ""
                client.emit(
                    ctx,
                    AgentTurnCompleted(
                        assistant_message=assistant_text,
                        input_tokens=0,
                        output_tokens=0,
                        tool_calls_made=0,
                        duration_ms=duration_ms,
                        stop_reason=stop_reason,
                    ),
                )
            return result

        return wrapped  # type: ignore[return-value]

    return decorator
