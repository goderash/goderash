# @goderash/adapter-claude-sdk

Audit handler for the [Anthropic TypeScript SDK](https://github.com/anthropics/anthropic-sdk-typescript).
Mirrors `goderash_adapter_anthropic` (Python).

```ts
import Anthropic from '@anthropic-ai/sdk'
import { GoderashClient } from '@goderash/sdk'
import { wrapAnthropic, auditMessagesResponse } from '@goderash/adapter-claude-sdk'

const goderash = new GoderashClient({ apiKey: '...', tenant: 'demo' })
const ctx = goderash.newContext()
const anthropic = wrapAnthropic({
  client: new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY! }),
  goderash,
  context: ctx,
})

const response = await anthropic.messages.create({
  model: 'claude-opus-4-7',
  max_tokens: 1024,
  messages: [{ role: 'user', content: 'hello' }],
})

// Or audit a response you already have:
auditMessagesResponse({ goderash, context: ctx, response })
```

Each `messages.create` call emits:

- `llm.call.started` (before the request)
- `llm.call.completed` (with token usage)
- `tool.invoked` for each `tool_use` block in the response

You are responsible for emitting the matching `tool.completed` / `tool.failed`
after your code runs each tool.
