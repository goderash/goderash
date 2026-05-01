"""Audited OpenAI Assistants run."""

from __future__ import annotations

import os

from openai import OpenAI

from goderash_adapter_openai import audit_assistants_run, wrap_openai
from goderash_sdk import GoderashClient


def main() -> None:
    goderash = GoderashClient(agent_id="openai-assistants-example")
    ctx = goderash.new_context()

    openai_client = OpenAI()
    wrap_openai(openai_client, goderash=goderash, context=ctx)

    assistant = openai_client.beta.assistants.create(
        name="Goderash demo",
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        instructions="You are a helpful assistant. Use tools when appropriate.",
        tools=[{"type": "code_interpreter"}],
    )
    thread = openai_client.beta.threads.create()
    openai_client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content="Compute the SHA-256 of 'goderash' as a hex string.",
    )
    run = openai_client.beta.threads.runs.create_and_poll(
        thread_id=thread.id,
        assistant_id=assistant.id,
    )

    audit_assistants_run(openai_client, goderash, ctx, run, thread_id=thread.id)
    goderash.flush_sync()
    print(f"[goderash] run audited; status={run.status}")


if __name__ == "__main__":
    main()
