"""Goderash adapter for the OpenAI Python SDK.

Two integration shapes:

1. **Wrapper** — wrap an `OpenAI` client; every `.chat.completions.create` /
   `.responses.create` call emits `llm.call.*` events.

2. **Assistants polling helper** — `audit_assistants_run(client, goderash, ctx, run)`
   iterates the run-step events and emits `tool.invoked` / `tool.completed`
   for every tool call.
"""

from .assistants import audit_assistants_run
from .wrapper import wrap_openai

__all__ = ["audit_assistants_run", "wrap_openai"]
