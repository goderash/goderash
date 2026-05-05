# goderash-adapter-langgraph

> LangGraph / LangChain callback that emits Goderash audit events.

[![PyPI version](https://img.shields.io/pypi/v/goderash-adapter-langgraph.svg)](https://pypi.org/project/goderash-adapter-langgraph/)
[![PyPI downloads](https://img.shields.io/pypi/dm/goderash-adapter-langgraph.svg)](https://pypi.org/project/goderash-adapter-langgraph/)
[![license](https://img.shields.io/pypi/l/goderash-adapter-langgraph.svg)](https://www.apache.org/licenses/LICENSE-2.0)

Drop-in adapter for [LangGraph](https://github.com/langchain-ai/langgraph) and [LangChain](https://github.com/langchain-ai/langchain). Plugs into LangChain's standard callback system, so every node, tool call, and LLM call your agent makes lands in [Goderash](https://github.com/goderash/goderash) — tamper-evident, hash-chained, regulator-ready.

Mirrors the TypeScript adapter [`@goderash/adapter-langgraph`](https://www.npmjs.com/package/@goderash/adapter-langgraph).

## Install

```bash
pip install goderash-sdk goderash-adapter-langgraph langgraph
```

## Quickstart

```python
import os
from goderash_sdk import GoderashClient
from goderash_adapter_langgraph import GoderashCallback
from langgraph.graph import StateGraph

goderash = GoderashClient(
    api_key=os.environ["GODERASH_API_KEY"],
    tenant="acme",
    agent_id="support-agent-v1",
)

callback = GoderashCallback(goderash)

graph = StateGraph(...).compile()

graph.invoke(
    {"messages": [{"role": "user", "content": "help me"}]},
    config={"callbacks": [callback]},
)
# → root chain start  → agent.turn.started
# → tool calls         → tool.invoked / tool.completed
# → LLM calls          → llm.call.started / llm.call.completed
# → root chain end     → agent.turn.completed
# All hash-chained into the per-tenant ledger.
```

## Events emitted

| LangChain callback | Goderash event |
|---|---|
| `on_chain_start` (root) | `agent.turn.started` |
| `on_chain_end` (root) | `agent.turn.completed` |
| `on_tool_start` | `tool.invoked` |
| `on_tool_end` | `tool.completed` |
| `on_tool_error` | `tool.failed` |
| `on_llm_start` | `llm.call.started` |
| `on_llm_end` | `llm.call.completed` (with token usage) |

Works for both sync `.invoke` and async `.ainvoke` paths.

## Compatibility

- `langchain-core >= 0.3.0`
- `langgraph >= 0.2.0`
- Python `>= 3.10`

## Related packages

- [`goderash-sdk`](https://pypi.org/project/goderash-sdk/) — core SDK + runtime guards
- [`goderash-adapter-anthropic`](https://pypi.org/project/goderash-adapter-anthropic/) — Anthropic Messages / Claude
- [`goderash-adapter-openai`](https://pypi.org/project/goderash-adapter-openai/) — OpenAI Chat / Responses / Assistants

## License

[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)
