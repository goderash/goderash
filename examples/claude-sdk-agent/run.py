"""Audited Anthropic Messages call (with optional tool use)."""

from __future__ import annotations

import sys

import anthropic

from goderash_adapter_anthropic import wrap_anthropic
from goderash_sdk import GoderashClient


def main() -> None:
    user_message = " ".join(sys.argv[1:]) or "Say hello in 5 words."

    goderash = GoderashClient(agent_id="claude-messages-example")
    ctx = goderash.new_context()

    client = anthropic.Anthropic()
    wrap_anthropic(client, goderash=goderash, context=ctx)

    resp = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=256,
        messages=[{"role": "user", "content": user_message}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    print("Assistant:", text)

    goderash.flush_sync()


if __name__ == "__main__":
    main()
