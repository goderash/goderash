# goderash-adapter-anthropic

> Goderash adapter for the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) — Messages + tool use.

[![PyPI version](https://img.shields.io/pypi/v/goderash-adapter-anthropic.svg)](https://pypi.org/project/goderash-adapter-anthropic/)
[![PyPI downloads](https://img.shields.io/pypi/dm/goderash-adapter-anthropic.svg)](https://pypi.org/project/goderash-adapter-anthropic/)
[![license](https://img.shields.io/pypi/l/goderash-adapter-anthropic.svg)](https://www.apache.org/licenses/LICENSE-2.0)

Drop-in adapter that audits every `messages.create` call to Claude via [Goderash](https://github.com/goderash/goderash) — tamper-evident, hash-chained, regulator-ready. Mirrors the TypeScript adapter [`@goderash/adapter-claude-sdk`](https://www.npmjs.com/package/@goderash/adapter-claude-sdk).

## Install

```bash
pip install goderash-adapter-anthropic
```

## Quickstart

```python
import os
import anthropic
from goderash_sdk import GoderashClient
from goderash_adapter_anthropic import wrap_anthropic, audit_messages_response

goderash = GoderashClient(
    api_key=os.environ["GODERASH_API_KEY"],
    tenant="acme",
    agent_id="claude-agent-v1",
)
ctx = goderash.new_context()

# Option 1 — wrap the client; every messages.create is audited automatically.
client = wrap_anthropic(
    client=anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]),
    goderash=goderash,
    context=ctx,
)

response = client.messages.create(
    model="claude-opus-4-7",
    max_tokens=1024,
    messages=[{"role": "user", "content": "hello"}],
)

# Option 2 — audit a response you already have.
audit_messages_response(goderash=goderash, context=ctx, response=response)
```

## Events emitted per `messages.create`

| Event | When | Payload includes |
|---|---|---|
| `llm.call.started` | Before the request leaves | model, max_tokens, message count |
| `llm.call.completed` | After the response | input_tokens, output_tokens, stop_reason |
| `tool.invoked` | One per `tool_use` block in the response | tool name, args, parent LLM call hash |

You are responsible for emitting the matching `tool.completed` / `tool.failed` after your code runs each tool. The `wrap_tool` decorator in `goderash-sdk` does this for you automatically.

## Streaming

Streaming is supported via `client.messages.stream(...)`. The adapter aggregates token usage and emits `llm.call.completed` when the stream closes.

## Compatibility

- `anthropic >= 0.40.0`
- Python `>= 3.10`
- Works with any Claude model (`claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5`, etc.)

## Related packages

- [`goderash-sdk`](https://pypi.org/project/goderash-sdk/) — core SDK + runtime guards
- [`goderash-adapter-openai`](https://pypi.org/project/goderash-adapter-openai/) — OpenAI Chat / Responses / Assistants
- [`goderash-adapter-langgraph`](https://pypi.org/project/goderash-adapter-langgraph/) — LangGraph callback

## License

[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)
