# @goderash/adapter-langgraph

> LangGraph.js / LangChain.js callback handler that emits Goderash audit events.

[![npm version](https://img.shields.io/npm/v/@goderash/adapter-langgraph.svg)](https://www.npmjs.com/package/@goderash/adapter-langgraph)
[![npm downloads](https://img.shields.io/npm/dw/@goderash/adapter-langgraph.svg)](https://www.npmjs.com/package/@goderash/adapter-langgraph)
[![license](https://img.shields.io/npm/l/@goderash/adapter-langgraph.svg)](https://www.apache.org/licenses/LICENSE-2.0)

Drop-in adapter for [LangGraph.js](https://github.com/langchain-ai/langgraphjs) and [LangChain.js](https://github.com/langchain-ai/langchainjs). Plugs into LangChain's standard callback system, so every node, tool call, and LLM call your agent makes lands in [Goderash](https://github.com/goderash/goderash) — tamper-evident, hash-chained, regulator-ready.

Mirrors the Python adapter: [`goderash-adapter-langgraph`](https://pypi.org/project/goderash-adapter-langgraph/).

## Install

```bash
npm i @goderash/sdk @goderash/adapter-langgraph @langchain/core
```

## Quickstart

```ts
import { GoderashClient } from '@goderash/sdk'
import { GoderashCallback } from '@goderash/adapter-langgraph'
import { StateGraph } from '@langchain/langgraph'

const goderash = new GoderashClient({
  apiKey: process.env.GODERASH_API_KEY!,
  tenant: 'acme',
  agentId: 'support-agent-v1',
})

const callback = new GoderashCallback({ client: goderash })

const graph = new StateGraph({ /* ... */ })
  .addNode(/* ... */)
  .compile()

await graph.invoke(
  { messages: [{ role: 'user', content: 'help me' }] },
  { callbacks: [callback] },
)
// → root chain start  → agent.turn.started
// → tool calls         → tool.invoked / tool.completed
// → LLM calls          → llm.call.started / llm.call.completed
// → root chain end     → agent.turn.completed
// All hash-chained into the per-tenant ledger.
```

## Events emitted

| LangChain callback | Goderash event |
|---|---|
| `handleChainStart` (root) | `agent.turn.started` |
| `handleChainEnd` (root) | `agent.turn.completed` |
| `handleToolStart` | `tool.invoked` |
| `handleToolEnd` | `tool.completed` |
| `handleToolError` | `tool.failed` |
| `handleLLMStart` | `llm.call.started` |
| `handleLLMEnd` | `llm.call.completed` (with token usage) |

## Compatibility

- `@langchain/core` `>= 0.3.0`
- LangGraph.js `>= 0.2.0`
- LangChain.js `>= 0.3.0`
- Node 18+, ESM

## Related packages

- [`@goderash/sdk`](https://www.npmjs.com/package/@goderash/sdk) — core SDK + runtime guards
- [`@goderash/adapter-claude-sdk`](https://www.npmjs.com/package/@goderash/adapter-claude-sdk) — Anthropic Messages / Claude SDK
- [`@goderash/adapter-openai-assistants`](https://www.npmjs.com/package/@goderash/adapter-openai-assistants) — OpenAI Assistants API

## License

[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)
