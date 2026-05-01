# LangGraph adapter

`goderash-adapter-langgraph` is a `BaseCallbackHandler` that routes LangChain /
LangGraph callbacks into Goderash.

## Install

```bash
pip install goderash-sdk goderash-adapter-langgraph
```

## Usage

```python
from goderash_sdk import GoderashClient
from goderash_adapter_langgraph import GoderashCallback
from langgraph.prebuilt import create_react_agent

goderash = GoderashClient(
    api_key="gdr_...",
    tenant="my-company",
    agent_id="support-agent-v1",
)

graph = create_react_agent(model, tools=[...])

ctx = goderash.new_context()                 # one per user turn
cb = GoderashCallback(goderash, context=ctx)

graph.invoke(
    {"messages": [("user", "what's my balance?")]},
    config={"callbacks": [cb]},
)

goderash.flush_sync()
```

## Event mapping

| LangChain callback | Goderash event |
|---|---|
| `on_chain_start` (root) | `agent.turn.started` |
| `on_chain_end` (root) | `agent.turn.completed` |
| `on_tool_start` | `tool.invoked` |
| `on_tool_end` | `tool.completed` |
| `on_tool_error` | `tool.failed` |
| `on_llm_start` | `llm.call.started` |
| `on_llm_end` | `llm.call.completed` |

Non-root chain events are ignored to keep the ledger focused on the agent's
top-level semantics.

## Extracting usage

LangChain emits token usage in `llm_output.token_usage`. The adapter picks
up `input_tokens` / `output_tokens` automatically. For providers that use
different keys (e.g. `prompt_tokens` + `completion_tokens`) the adapter maps
those, too.

## Context re-use

If you want the entire lifetime of a graph (across multiple user turns) to
share a `conversation_id`, reuse the same `GoderashContext`:

```python
ctx = goderash.new_context(conversation_id="conv-123")  # fixed conversation
cb = GoderashCallback(goderash, context=ctx)

# Mutate turn_id per user-turn if you want finer grouping:
for i, user_msg in enumerate(stream_of_user_messages):
    ctx = cb.goderash_context  # same conversation_id, new turn_id as you set
    graph.invoke(..., config={"callbacks": [cb]})
```

## Limitations of v1

- Tool category is always reported as `"query"` — override by wrapping
  action tools with `wrap_tool(..., category="action")`.
- Permission events are not emitted by the adapter; wrap your own gate and
  emit `PermissionGranted` / `PermissionDenied` explicitly.
