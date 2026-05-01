"""`@wrap_tool` — turns a callable into an audited tool.

Every call emits `tool.invoked`, then either `tool.completed` or `tool.failed`.
Args + results are hashed (not stored raw) unless `redact=False` and
`include_preview=True`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, Literal, TypeVar, overload

from ..client import GoderashClient, GoderashContext
from ..events import ToolCompleted, ToolFailed, ToolInvoked

F = TypeVar("F", bound=Callable[..., Any])

Category = Literal["query", "action", "intelligence"]
Confirmation = Literal["none", "pin", "biometric", "otp"]


def _hash_args(args: tuple, kwargs: dict[str, Any]) -> str:
    blob = json.dumps(
        {"args": list(args), "kwargs": kwargs},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _hash_result(result: Any) -> str:
    try:
        blob = json.dumps(result, sort_keys=True, default=str, separators=(",", ":"))
    except TypeError:
        blob = repr(result)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _truncate_preview(obj: Any, max_bytes: int = 2048) -> dict[str, Any] | None:
    try:
        blob = json.dumps(obj, default=str, separators=(",", ":"))
    except Exception:
        return None
    if len(blob.encode("utf-8")) > max_bytes:
        return None
    try:
        return {"value": obj}
    except Exception:
        return None


@overload
def wrap_tool(
    client: GoderashClient,
    *,
    name: str | None = None,
    category: Category = "query",
    confirmation: Confirmation = "none",
    context: GoderashContext | None = None,
    include_preview: bool = False,
) -> Callable[[F], F]: ...


def wrap_tool(
    client: GoderashClient,
    *,
    name: str | None = None,
    category: Category = "query",
    confirmation: Confirmation = "none",
    context: GoderashContext | None = None,
    include_preview: bool = False,
) -> Callable[[F], F]:
    """Decorator. Supports sync + async callables."""

    def decorator(fn: F) -> F:
        tool_name = name or fn.__name__

        if asyncio.iscoroutinefunction(fn):

            @wraps(fn)
            async def awrapped(*args: Any, **kwargs: Any) -> Any:
                ctx = kwargs.pop("_goderash_context", None) or context
                if ctx is None:
                    return await fn(*args, **kwargs)

                started_at = time.perf_counter()
                args_hash = _hash_args(args, kwargs)
                client.emit(
                    ctx,
                    ToolInvoked(
                        tool_name=tool_name,
                        tool_category=category,
                        input_args_hash=args_hash,
                        input_args_preview=(_truncate_preview(kwargs) if include_preview else None),
                        confirmation_type=confirmation,
                    ),
                )
                try:
                    result = await fn(*args, **kwargs)
                except Exception as exc:
                    duration_ms = int((time.perf_counter() - started_at) * 1000)
                    client.emit(
                        ctx,
                        ToolFailed(
                            tool_name=tool_name,
                            error_class=type(exc).__name__,
                            error_message=str(exc)[:1024],
                            duration_ms=duration_ms,
                        ),
                    )
                    raise

                duration_ms = int((time.perf_counter() - started_at) * 1000)
                client.emit(
                    ctx,
                    ToolCompleted(
                        tool_name=tool_name,
                        success=True,
                        duration_ms=duration_ms,
                        result_hash=_hash_result(result),
                        result_preview=(_truncate_preview(result) if include_preview else None),
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
            args_hash = _hash_args(args, kwargs)
            client.emit(
                ctx,
                ToolInvoked(
                    tool_name=tool_name,
                    tool_category=category,
                    input_args_hash=args_hash,
                    input_args_preview=(_truncate_preview(kwargs) if include_preview else None),
                    confirmation_type=confirmation,
                ),
            )
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                duration_ms = int((time.perf_counter() - started_at) * 1000)
                client.emit(
                    ctx,
                    ToolFailed(
                        tool_name=tool_name,
                        error_class=type(exc).__name__,
                        error_message=str(exc)[:1024],
                        duration_ms=duration_ms,
                    ),
                )
                raise

            duration_ms = int((time.perf_counter() - started_at) * 1000)
            client.emit(
                ctx,
                ToolCompleted(
                    tool_name=tool_name,
                    success=True,
                    duration_ms=duration_ms,
                    result_hash=_hash_result(result),
                    result_preview=(_truncate_preview(result) if include_preview else None),
                ),
            )
            return result

        return wrapped  # type: ignore[return-value]

    return decorator
