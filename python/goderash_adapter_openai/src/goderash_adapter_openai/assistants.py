"""Walk an OpenAI Assistants run and emit Goderash events for each step.

Usage::

    from openai import OpenAI
    from goderash_sdk import GoderashClient
    from goderash_adapter_openai import audit_assistants_run

    client = OpenAI()
    goderash = GoderashClient(...)
    ctx = goderash.new_context()

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread.id, assistant_id=assistant.id
    )
    audit_assistants_run(client, goderash, ctx, run, thread_id=thread.id)
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from goderash_sdk import GoderashClient, GoderashContext
from goderash_sdk.events import ToolCompleted, ToolFailed, ToolInvoked

if TYPE_CHECKING:  # pragma: no cover
    from openai import OpenAI  # type: ignore[import-not-found]


def _hash(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def audit_assistants_run(
    openai_client: OpenAI,
    goderash: GoderashClient,
    context: GoderashContext,
    run: Any,
    *,
    thread_id: str,
) -> None:
    """Read all run steps for a completed run and emit Goderash tool events.

    Designed to be called after `create_and_poll` (or after `retrieve_run`
    returns a terminal status). Walks `runs.steps.list` in chronological order.
    """
    steps = openai_client.beta.threads.runs.steps.list(
        thread_id=thread_id,
        run_id=run.id,
        order="asc",
        limit=100,
    )

    for step in getattr(steps, "data", []) or []:
        step_type = getattr(step, "type", None)
        details = getattr(step, "step_details", None)
        if step_type != "tool_calls" or details is None:
            continue

        for call in getattr(details, "tool_calls", None) or []:
            tool_type = getattr(call, "type", "function")
            if tool_type == "function":
                fn = getattr(call, "function", None)
                tool_name = getattr(fn, "name", "unknown")
                args = getattr(fn, "arguments", "")
                output = getattr(fn, "output", None)
                goderash.emit(
                    context,
                    ToolInvoked(
                        tool_name=str(tool_name),
                        tool_category="query",
                        input_args_hash=_hash(args),
                    ),
                )
                if output is not None:
                    goderash.emit(
                        context,
                        ToolCompleted(
                            tool_name=str(tool_name),
                            success=True,
                            duration_ms=0,
                            result_hash=_hash(output),
                        ),
                    )
            elif tool_type in ("code_interpreter", "file_search", "retrieval"):
                goderash.emit(
                    context,
                    ToolInvoked(
                        tool_name=str(tool_type),
                        tool_category="intelligence",
                        input_args_hash=_hash(getattr(call, "id", "")),
                    ),
                )
                goderash.emit(
                    context,
                    ToolCompleted(
                        tool_name=str(tool_type),
                        success=True,
                        duration_ms=0,
                        result_hash=_hash(getattr(call, "id", "")),
                    ),
                )

    if getattr(run, "status", "") == "failed":
        last_error = getattr(run, "last_error", None)
        goderash.emit(
            context,
            ToolFailed(
                tool_name="assistants_run",
                error_class=str(getattr(last_error, "code", "unknown")),
                error_message=str(getattr(last_error, "message", "unknown"))[:1024],
                duration_ms=0,
            ),
        )
