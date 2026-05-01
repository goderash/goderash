# @goderash/adapter-openai-assistants

Audit handler for the [OpenAI Node SDK](https://github.com/openai/openai-node)
Assistants API. Mirrors `goderash_adapter_openai` (Python).

```ts
import OpenAI from 'openai'
import { GoderashClient } from '@goderash/sdk'
import { auditAssistantsRun } from '@goderash/adapter-openai-assistants'

const goderash = new GoderashClient({ apiKey: '...', tenant: 'demo' })
const ctx = goderash.newContext()
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY! })

const thread = await openai.beta.threads.create()
await openai.beta.threads.messages.create(thread.id, { role: 'user', content: 'hi' })

const run = await openai.beta.threads.runs.createAndPoll(thread.id, {
  assistant_id: assistant.id,
})

await auditAssistantsRun({
  client: openai,
  goderash,
  context: ctx,
  run,
  threadId: thread.id,
})

await goderash.flush()
```

For each step in the run, this emits one `tool.invoked` (and a matching
`tool.completed`) per `function`, `code_interpreter`, `file_search`, or
`retrieval` tool call. Failed runs also emit a `tool.failed`.
