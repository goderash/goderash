# @goderash/sdk

> Audit any AI agent with one import. Tamper-evident, hash-chained, regulator-ready.

[![npm version](https://img.shields.io/npm/v/@goderash/sdk.svg)](https://www.npmjs.com/package/@goderash/sdk)
[![npm downloads](https://img.shields.io/npm/dw/@goderash/sdk.svg)](https://www.npmjs.com/package/@goderash/sdk)
[![license](https://img.shields.io/npm/l/@goderash/sdk.svg)](https://www.apache.org/licenses/LICENSE-2.0)

[Goderash](https://github.com/goderash/goderash) is the audit & governance fabric for regulated AI agents. One decorator turns every tool call, LLM call, and policy decision into a typed, immutable, SHA-256 hash-chained event in a per-tenant ledger. From there: signed evidence packs for **SOC 2, HIPAA, FFIEC, FINRA, and SEC Rule 17a-4** in one click.

- 🌐 **Live demo:** [ai.goderash.com](https://ai.goderash.com)
- 📚 **Repo:** [github.com/goderash/goderash](https://github.com/goderash/goderash)
- 🐍 **Python:** [`goderash-sdk`](https://pypi.org/project/goderash-sdk/)

## Install

```bash
npm i @goderash/sdk
# or
pnpm add @goderash/sdk
# or
yarn add @goderash/sdk
```

## 60-second quickstart

```ts
import { GoderashClient, wrapTool } from '@goderash/sdk'

const goderash = new GoderashClient({
  apiKey: process.env.GODERASH_API_KEY!,
  tenant: 'acme-finance',
  agentId: 'portfolio-advisor-v1',
})

const transferMoney = wrapTool(
  goderash,
  { name: 'transfer_money', category: 'action', confirmation: 'biometric' },
  async (src: string, dst: string, amount: number) => {
    // ... your logic ...
    return { status: 'queued' }
  },
)

const ctx = goderash.newContext()
await transferMoney('checking', 'savings', 100, { goderashContext: ctx })
// → emits: tool.invoked, tool.completed
// → hash-chained into the per-tenant ledger
// → ready to be included in your next SOC 2 / HIPAA evidence pack
```

## What `wrap*` does

| Decorator | What it wraps | Events emitted |
|---|---|---|
| `wrapTool` | Any function the agent can call | `tool.invoked`, `tool.completed` / `tool.failed`, plus any `contract.violated` events |
| `wrapLLM` | Your LLM call (OpenAI, Anthropic, etc.) | `llm.call.started`, `llm.call.completed` (with token usage) |
| `wrapAgent` | The full agent turn boundary | `agent.turn.started`, `agent.turn.completed` (parent of every tool/LLM event in the turn) |

Every event carries `tenant_id`, `agent_id`, `conversation_id`, `turn_id`, `parent_event_id`, `occurred_at`, `recorded_at`, `prev_hash`, `hash` — the chain-of-custody auditors require.

## Runtime guards

The same SDK ships the runtime safety stack we built for an AI banking agent in production:

```ts
import {
  GuardChain,
  FraudGuard,
  PermissionModeGate,
  VelocityLimiter,
  ConversationBudget,
  CancellationToken,
} from '@goderash/sdk/guards'

const guards = new GuardChain([
  new PermissionModeGate({ mode: 'STRICT' }),
  new FraudGuard(),
  new VelocityLimiter({
    rules: {
      transfer_money: [{ windowSec: 3600, maxCount: 5, label: '5/hour' }],
    },
  }),
  new ConversationBudget({ maxToolCalls: 20, maxTokens: 200_000 }),
])

const decision = await guards.evaluate(goderash, ctx, {
  tool: 'transfer_money',
  input: { amount: 500 },
})
if (decision.allow) {
  await transferMoney(...)
}
```

| Guard | What it stops |
|---|---|
| `PermissionModeGate` | Tools your current mode (`PLAN` / `DEFAULT` / `AUTO` / `STRICT`) doesn't authorize |
| `FraudGuard` | Pattern-based attack signatures at the input boundary |
| `VelocityLimiter` | Per-tool rate limit (Redis-backed in production) |
| `ConversationBudget` | Runaway loops (max tool calls, max tokens per conversation) |
| `CancellationToken` | Irreversible actions cancelled mid-flight |

## Drop-in framework adapters

| Framework | Package |
|---|---|
| Anthropic Messages / Claude SDK | [`@goderash/adapter-claude-sdk`](https://www.npmjs.com/package/@goderash/adapter-claude-sdk) |
| OpenAI Assistants | [`@goderash/adapter-openai-assistants`](https://www.npmjs.com/package/@goderash/adapter-openai-assistants) |
| LangGraph.js / LangChain.js | [`@goderash/adapter-langgraph`](https://www.npmjs.com/package/@goderash/adapter-langgraph) |

## License

[Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0)
