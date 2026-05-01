/**
 * @goderash/adapter-langgraph — LangChain.js / LangGraph.js callback handler.
 *
 * Routes LangChain JS callbacks into the Goderash ledger. Mirrors the Python
 * adapter under `python/goderash_adapter_langgraph/`.
 */

import type { GoderashClient, GoderashContext } from '@goderash/sdk'

type AnyDict = Record<string, unknown>

export interface GoderashCallbackOptions {
  client: GoderashClient
  context?: GoderashContext
}

interface SerializedRunnable {
  id?: string[]
  name?: string
  kwargs?: AnyDict
}

interface RunnableMessage {
  type?: string
  content?: unknown
  _getType?: () => string
}

/**
 * Implements the subset of LangChain's `BaseCallbackHandler` we care about.
 * Typed loosely so it works across `@langchain/core` minor versions.
 */
export class GoderashCallback {
  readonly name = 'GoderashCallback'
  readonly client: GoderashClient
  readonly context: GoderashContext

  private readonly started = new Map<string, number>()
  private rootRunId: string | null = null

  constructor(opts: GoderashCallbackOptions) {
    this.client = opts.client
    this.context = opts.context ?? opts.client.newContext()
  }

  // ---- Chain (root chain == agent turn) ----

  handleChainStart(
    _serialized: SerializedRunnable | undefined,
    inputs: AnyDict,
    runId: string,
    parentRunId?: string,
  ): void {
    if (parentRunId == null && this.rootRunId == null) {
      this.rootRunId = runId
      this.started.set(runId, performance.now())
      this.client.emit(this.context, {
        event_type: 'agent.turn.started',
        user_message: extractUserMessage(inputs),
      })
    }
  }

  handleChainEnd(outputs: AnyDict, runId: string, parentRunId?: string): void {
    if (parentRunId == null && runId === this.rootRunId) {
      const startedAt = this.started.get(runId) ?? performance.now()
      const durationMs = Math.round(performance.now() - startedAt)
      this.client.emit(this.context, {
        event_type: 'agent.turn.completed',
        assistant_message: extractAssistant(outputs),
        input_tokens: 0,
        output_tokens: 0,
        tool_calls_made: 0,
        duration_ms: durationMs,
        stop_reason: 'end_turn',
      })
      this.rootRunId = null
      this.started.delete(runId)
    }
  }

  handleChainError(_err: unknown, runId: string, parentRunId?: string): void {
    if (parentRunId == null && runId === this.rootRunId) {
      const startedAt = this.started.get(runId) ?? performance.now()
      const durationMs = Math.round(performance.now() - startedAt)
      this.client.emit(this.context, {
        event_type: 'agent.turn.completed',
        assistant_message: '',
        input_tokens: 0,
        output_tokens: 0,
        tool_calls_made: 0,
        duration_ms: durationMs,
        stop_reason: 'error',
      })
      this.rootRunId = null
      this.started.delete(runId)
    }
  }

  // ---- Tool ----

  handleToolStart(
    serialized: SerializedRunnable | undefined,
    inputStr: string,
    runId: string,
  ): void {
    this.started.set(runId, performance.now())
    this.client.emit(this.context, {
      event_type: 'tool.invoked',
      tool_name: pickName(serialized),
      tool_category: 'query',
      input_args_hash: simpleHash(inputStr),
    })
  }

  handleToolEnd(output: string, runId: string, _parentRunId?: string, name?: string): void {
    const startedAt = this.started.get(runId) ?? performance.now()
    const durationMs = Math.round(performance.now() - startedAt)
    this.started.delete(runId)
    this.client.emit(this.context, {
      event_type: 'tool.completed',
      tool_name: name ?? 'unknown_tool',
      success: true,
      duration_ms: durationMs,
      result_hash: simpleHash(output),
    })
  }

  handleToolError(err: unknown, runId: string, _parentRunId?: string, name?: string): void {
    const startedAt = this.started.get(runId) ?? performance.now()
    const durationMs = Math.round(performance.now() - startedAt)
    this.started.delete(runId)
    const e = err instanceof Error ? err : new Error(String(err))
    this.client.emit(this.context, {
      event_type: 'tool.failed',
      tool_name: name ?? 'unknown_tool',
      error_class: e.constructor.name,
      error_message: e.message.slice(0, 1024),
      duration_ms: durationMs,
    })
  }

  // ---- LLM ----

  handleLLMStart(
    serialized: SerializedRunnable | undefined,
    _prompts: string[],
    runId: string,
  ): void {
    this.started.set(runId, performance.now())
    this.client.emit(this.context, {
      event_type: 'llm.call.started',
      provider: inferProvider(serialized),
      model: pickModel(serialized),
    })
  }

  handleLLMEnd(response: AnyDict, runId: string): void {
    const startedAt = this.started.get(runId) ?? performance.now()
    const durationMs = Math.round(performance.now() - startedAt)
    this.started.delete(runId)
    const usage = extractUsage(response)
    this.client.emit(this.context, {
      event_type: 'llm.call.completed',
      provider: usage.provider,
      model: usage.model,
      input_tokens: usage.inputTokens,
      output_tokens: usage.outputTokens,
      cache_read_tokens: usage.cacheReadTokens,
      cache_creation_tokens: usage.cacheCreationTokens,
      duration_ms: durationMs,
      stop_reason: null,
    })
  }
}

// ---- helpers --------------------------------------------------------------

function pickName(serialized: SerializedRunnable | undefined): string {
  if (!serialized) return 'unknown_tool'
  const id = serialized.id ?? []
  const last = id.length > 0 ? String(id[id.length - 1]) : ''
  return serialized.name ?? last ?? 'unknown_tool'
}

function pickModel(serialized: SerializedRunnable | undefined): string {
  if (!serialized) return 'unknown'
  const kwargs = serialized.kwargs ?? {}
  const model = (kwargs.model as string | undefined) ?? (kwargs.modelName as string | undefined)
  return model ?? 'unknown'
}

function inferProvider(serialized: SerializedRunnable | undefined): string {
  if (!serialized) return 'unknown'
  const id = serialized.id ?? []
  const last = (id.length > 0 ? String(id[id.length - 1]) : '').toLowerCase()
  if (last.includes('anthropic')) return 'anthropic'
  if (last.includes('openai')) return 'openai'
  if (last.includes('google') || last.includes('vertex')) return 'google'
  return 'unknown'
}

function extractUserMessage(inputs: AnyDict): string {
  for (const key of ['input', 'query', 'message', 'user_message']) {
    const v = inputs[key]
    if (typeof v === 'string') return v
  }
  const messages = inputs.messages as Array<RunnableMessage> | undefined
  if (Array.isArray(messages)) {
    for (const m of messages) {
      const kind = m.type ?? m._getType?.()
      if (kind === 'human' && typeof m.content === 'string') {
        return m.content
      }
    }
  }
  return ''
}

function extractAssistant(outputs: AnyDict): string {
  for (const key of ['output', 'result', 'answer']) {
    const v = outputs[key]
    if (typeof v === 'string') return v
  }
  const messages = outputs.messages as Array<RunnableMessage> | undefined
  if (Array.isArray(messages) && messages.length > 0) {
    const last = messages[messages.length - 1]
    if (last && typeof last.content === 'string') return last.content
  }
  return ''
}

function extractUsage(response: AnyDict): {
  provider: string
  model: string
  inputTokens: number
  outputTokens: number
  cacheReadTokens: number
  cacheCreationTokens: number
} {
  const llmOutput = (response.llmOutput as AnyDict | undefined) ?? {}
  const usage = (llmOutput.tokenUsage as AnyDict | undefined) ?? {}

  return {
    provider: (llmOutput.provider as string | undefined) ?? 'unknown',
    model: (llmOutput.model_name as string | undefined) ?? 'unknown',
    inputTokens: numeric(usage.promptTokens ?? usage.inputTokens),
    outputTokens: numeric(usage.completionTokens ?? usage.outputTokens),
    cacheReadTokens: numeric(usage.cacheReadInputTokens),
    cacheCreationTokens: numeric(usage.cacheCreationInputTokens),
  }
}

function numeric(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

function simpleHash(s: string): string {
  // djb2 — opaque identifier, not a cryptographic hash. The control plane
  // re-hashes payloads with SHA-256 on append.
  let h = 5381
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) | 0
  }
  return Math.abs(h).toString(16).padStart(8, '0').repeat(8)
}
