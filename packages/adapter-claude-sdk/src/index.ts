/**
 * @goderash/adapter-claude-sdk — audit Anthropic Claude responses.
 *
 * Wraps an `Anthropic` client so every `messages.create` call emits
 * `llm.call.started` / `llm.call.completed`, and every `tool_use` block in
 * the response emits `tool.invoked`. Mirrors the Python adapter under
 * `python/goderash_adapter_anthropic/`.
 */

import { createHash } from 'node:crypto'
import type { GoderashClient, GoderashContext } from '@goderash/sdk'

type AnyDict = Record<string, unknown>

interface MessagesAPI {
  create: (...args: unknown[]) => Promise<AnyDict> | AnyDict
  _goderashOrigCreate?: (...args: unknown[]) => Promise<AnyDict> | AnyDict
}

interface AnthropicLike {
  messages: MessagesAPI
}

export interface WrapAnthropicOptions {
  client: AnthropicLike
  goderash: GoderashClient
  context: GoderashContext
  provider?: string
}

/**
 * Replace `client.messages.create` with an audited proxy. The original
 * method stays accessible as `client.messages._goderashOrigCreate`.
 *
 * Returns the same client instance for chaining.
 */
export function wrapAnthropic<T extends AnthropicLike>(opts: WrapAnthropicOptions): T {
  const { client, goderash, context, provider = 'anthropic' } = opts
  const target = client.messages
  const original = target.create.bind(target)
  target._goderashOrigCreate = original

  target.create = async (...args: unknown[]): Promise<AnyDict> => {
    const kwargs = (args[0] as AnyDict | undefined) ?? {}
    const model = String(kwargs.model ?? 'unknown')
    const startedAt = performance.now()

    goderash.emit(context, {
      event_type: 'llm.call.started',
      provider,
      model,
    })

    try {
      const result = (await original(...args)) as AnyDict
      const durationMs = Math.round(performance.now() - startedAt)
      auditMessagesResponse({
        goderash,
        context,
        response: result,
        provider,
        model,
        durationMs,
      })
      return result
    } catch (err: unknown) {
      const durationMs = Math.round(performance.now() - startedAt)
      const e = err instanceof Error ? err : new Error(String(err))
      goderash.emit(context, {
        event_type: 'llm.call.completed',
        provider,
        model,
        input_tokens: 0,
        output_tokens: 0,
        duration_ms: durationMs,
        stop_reason: 'error',
      })
      goderash.emit(context, {
        event_type: 'tool.failed',
        tool_name: 'anthropic.messages.create',
        error_class: e.constructor.name,
        error_message: e.message.slice(0, 1024),
        duration_ms: durationMs,
      })
      throw err
    }
  }

  return client as T
}

export interface AuditMessagesResponseOptions {
  goderash: GoderashClient
  context: GoderashContext
  response: AnyDict
  provider?: string
  model?: string
  durationMs?: number
}

/**
 * Emit one `llm.call.completed` plus one `tool.invoked` per `tool_use` block.
 *
 * The tool_use blocks are *requests* — your code is responsible for emitting
 * the matching `tool.completed` / `tool.failed` after running the tool.
 */
export function auditMessagesResponse(opts: AuditMessagesResponseOptions): void {
  const { goderash, context, response, provider = 'anthropic', model, durationMs = 0 } = opts
  const usage = (response.usage as AnyDict | undefined) ?? {}
  const stopReason = response.stop_reason

  goderash.emit(context, {
    event_type: 'llm.call.completed',
    provider,
    model: String(model ?? response.model ?? 'unknown'),
    input_tokens: numeric(usage.input_tokens),
    output_tokens: numeric(usage.output_tokens),
    cache_read_tokens: numeric(usage.cache_read_input_tokens),
    cache_creation_tokens: numeric(usage.cache_creation_input_tokens),
    duration_ms: durationMs,
    stop_reason: typeof stopReason === 'string' ? stopReason : null,
  })

  const blocks = Array.isArray(response.content) ? (response.content as AnyDict[]) : []
  for (const block of blocks) {
    if (block.type === 'tool_use') {
      goderash.emit(context, {
        event_type: 'tool.invoked',
        tool_name: String(block.name ?? 'unknown'),
        tool_category: 'query',
        input_args_hash: sha256Hex(block.input ?? {}),
      })
    }
  }
}

// ---- helpers --------------------------------------------------------------

function numeric(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0
}

function sha256Hex(obj: unknown): string {
  const blob = JSON.stringify(obj, Object.keys(obj as object).sort())
  return createHash('sha256').update(blob ?? 'null').digest('hex')
}
