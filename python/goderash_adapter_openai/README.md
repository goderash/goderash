# goderash-adapter-openai

> Goderash adapter for the [OpenAI Python SDK](https://github.com/openai/openai-python) — Chat Completions, Responses, and Assistants APIs.

[![PyPI version](https://img.shields.io/pypi/v/goderash-adapter-openai.svg)](https://pypi.org/project/goderash-adapter-openai/)
[![PyPI downloads](https://img.shields.io/pypi/dm/goderash-adapter-openai.svg)](https://pypi.org/project/goderash-adapter-openai/)
[![license](https://img.shields.io/pypi/l/goderash-adapter-openai.svg)](https://www.apache.org/licenses/LICENSE-2.0)

Drop-in adapter that audits every OpenAI call via [Goderash](https://github.com/goderash/goderash) — tamper-evident, hash-chained, regulator-ready. Covers all three modern OpenAI surfaces: Chat Completions, Responses API, and Assistants API.

## Install

```bash
pip install goderash-adapter-openai
```

## Two integration shapes

### 1. Wrapper — for Chat Completions and Responses

Wrap your `OpenAI` client; every `.chat.completions.create` and `.responses.create` call emits `llm.call.*` events automatically.

```python
import os
from openai import OpenAI
from goderash_sdk import GoderashClient
from goderash_adapter_openai import wrap_openai

goderash = GoderashClient(
    api_key=os.environ["GODERASH_API_KEY"],
    tenant="acme",
    agent_id="openai-agent-v1",
)
ctx = goderash.new_context()

client = wrap_openai(
    OpenAI(api_key=os.environ["OPENAI_API_KEY"]),
    goderash=goderash,
    context=ctx,
)

response = client.chat.completions.create(
    model="gpt-4.1",
    messages=[{"role": "user", "content": "hello"}],
)
# → llm.call.started + llm.call.completed (with token usage)
```

### 2. Assistants polling helper

For the Assistants API, audit a completed run end-to-end. Iterates run-step events and emits `tool.invoked` / `tool.completed` for every function, code_interpreter, file_search, and retrieval call.

```python
from openai import OpenAI
from goderash_sdk import GoderashClient
from goderash_adapter_openai import audit_assistants_run

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
goderash = GoderashClient(...)
ctx = goderash.new_context()

thread = client.beta.threads.create()
client.beta.threads.messages.create(thread.id, role="user", content="hi")

run = client.beta.threads.runs.create_and_poll(
    thread_id=thread.id,
    assistant_id=assistant.id,
)

audit_assistants_run(
    client=client,
    goderash=goderash,
    context=ctx,
    run=run,
    thread_id=thread.id,
)

goderash.flush()
```

Failed runs also emit `tool.failed` for any erroring step.

## Events emitted

| Surface | Event | When |
|---|---|---|
| Chat / Responses | `llm.call.started` | Before request |
| Chat / Responses | `llm.call.completed` | After response, with token usage |
| Assistants | `tool.invoked` | Per function / code_interpreter / file_search / retrieval call |
| Assistants | `tool.completed` | After tool succeeds |
| Assistants | `tool.failed` | On run failure |

## Compatibility

- `openai >= 1.50.0`
- Python `>= 3.10`
- Works with any OpenAI model (gpt-4.1, gpt-4o, o1, o3, etc.)

## Related packages

- [`goderash-sdk`](https://pypi.org/project/goderash-sdk/) — core SDK + runtime guards
- [`goderash-adapter-anthropic`](https://pypi.org/project/goderash-adapter-anthropic/) — Anthropic Messages / Claude
- [`goderash-adapter-langgraph`](https://pypi.org/project/goderash-adapter-langgraph/) — LangGraph callback

## License

[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)
