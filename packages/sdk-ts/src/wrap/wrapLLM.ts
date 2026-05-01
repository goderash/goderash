/**
 * wrapLLM — audit an LLM-calling function.
 */

import type { GoderashClient, GoderashContext } from '../client.js'

export interface WrapLLMOptions {
  provider: string
  model: string
  context?: GoderashContext
  extractTokens?: (result: unknown) => {
    inputTokens?: number
    outputTokens?: number
    cacheReadTokens?: number
    cacheCreationTokens?: number
    stopReason?: string | null
  }
}

type AnyFn<A extends unknown[], R> = (...args: A) => Promise<R> | R

export function wrapLLM<A extends unknown[], R>(
  client: GoderashClient,
  opts: WrapLLMOptions,
  fn: AnyFn<A, R>,
): (...args: A) => Promise<R> {
  const extract = opts.extractTokens ?? defaultExtractTokens

  return async function wrapped(...args: A): Promise<R> {
    const ctx = opts.context
    if (!ctx) return await Promise.resolve(fn(...args))

    const started = performance.now()
    client.emit(ctx, {
      event_type: 'llm.call.started',
      provider: opts.provider,
      model: opts.model,
    })

    const result = await Promise.resolve(fn(...args))
    const durationMs = Math.round(performance.now() - started)
    const usage = extract(result)
    client.emit(ctx, {
      event_type: 'llm.call.completed',
      provider: opts.provider,
      model: opts.model,
      input_tokens: usage.inputTokens ?? 0,
      output_tokens: usage.outputTokens ?? 0,
      cache_read_tokens: usage.cacheReadTokens ?? 0,
      cache_creation_tokens: usage.cacheCreationTokens ?? 0,
      duration_ms: durationMs,
      stop_reason: usage.stopReason ?? null,
    })

    return result
  }
}

function defaultExtractTokens(result: unknown): {
  inputTokens?: number
  outputTokens?: number
  cacheReadTokens?: number
  cacheCreationTokens?: number
  stopReason?: string | null
} {
  if (typeof result !== 'object' || result === null) return {}
  const r = result as Record<string, unknown>
  const usage = (r.usage as Record<string, number> | undefined) ?? undefined
  return {
    inputTokens: (usage?.input_tokens as number) ?? (r.input_tokens as number) ?? 0,
    outputTokens: (usage?.output_tokens as number) ?? (r.output_tokens as number) ?? 0,
    cacheReadTokens:
      (usage?.cache_read_input_tokens as number) ?? (r.cache_read_tokens as number) ?? 0,
    cacheCreationTokens:
      (usage?.cache_creation_input_tokens as number) ?? (r.cache_creation_tokens as number) ?? 0,
    stopReason: (r.stop_reason as string) ?? null,
  }
}
