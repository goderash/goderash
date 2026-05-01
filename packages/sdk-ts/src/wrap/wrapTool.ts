/**
 * wrapTool — turn any async function into an audited tool.
 */

import type { GoderashClient, GoderashContext } from '../client.js'
import type { ConfirmationType, ToolCategory } from '../events/types.js'
import { hashJson } from '../utils/hash.js'

export interface WrapToolOptions {
  name?: string
  category?: ToolCategory
  confirmation?: ConfirmationType
  context?: GoderashContext
  includePreview?: boolean
}

type AnyFn<A extends unknown[], R> = (...args: A) => Promise<R> | R

export function wrapTool<A extends unknown[], R>(
  client: GoderashClient,
  opts: WrapToolOptions,
  fn: AnyFn<A, R>,
): (...args: A) => Promise<R> {
  const toolName = opts.name ?? (fn.name || 'anonymous_tool')
  const category = opts.category ?? 'query'
  const confirmation = opts.confirmation ?? 'none'

  return async function wrapped(...args: A): Promise<R> {
    const ctx = opts.context
    if (!ctx) return await Promise.resolve(fn(...args))

    const started = performance.now()
    const inputHash = await hashJson(args)

    client.emit(ctx, {
      event_type: 'tool.invoked',
      tool_name: toolName,
      tool_category: category,
      input_args_hash: inputHash,
      confirmation_type: confirmation,
      input_args_preview: opts.includePreview ? { args } : null,
    })

    try {
      const result = await Promise.resolve(fn(...args))
      const durationMs = Math.round(performance.now() - started)
      client.emit(ctx, {
        event_type: 'tool.completed',
        tool_name: toolName,
        success: true,
        duration_ms: durationMs,
        result_hash: await hashJson(result),
        result_preview: opts.includePreview ? { result } : null,
      })
      return result
    } catch (err) {
      const durationMs = Math.round(performance.now() - started)
      client.emit(ctx, {
        event_type: 'tool.failed',
        tool_name: toolName,
        error_class: err instanceof Error ? err.constructor.name : 'Error',
        error_message: (err instanceof Error ? err.message : String(err)).slice(0, 1024),
        duration_ms: durationMs,
      })
      throw err
    }
  }
}
