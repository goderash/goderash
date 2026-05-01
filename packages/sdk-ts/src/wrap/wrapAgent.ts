/**
 * wrapAgent — brackets a user turn with agent.turn.started / completed.
 */

import type { GoderashClient, GoderashContext } from '../client.js'

export interface WrapAgentOptions {
  context?: GoderashContext
  language?: string
}

type TurnFn<R> = (
  userMessage: string,
  ctx: GoderashContext,
) => Promise<R> | R

export function wrapAgent<R>(
  client: GoderashClient,
  opts: WrapAgentOptions,
  fn: TurnFn<R>,
): (userMessage: string) => Promise<R> {
  return async function runTurn(userMessage: string): Promise<R> {
    const ctx = opts.context ?? client.newContext()
    const started = performance.now()

    client.emit(ctx, {
      event_type: 'agent.turn.started',
      user_message: userMessage,
      language: opts.language ?? null,
    })

    let stopReason: 'end_turn' | 'error' = 'end_turn'
    try {
      const result = await Promise.resolve(fn(userMessage, ctx))
      const durationMs = Math.round(performance.now() - started)
      client.emit(ctx, {
        event_type: 'agent.turn.completed',
        assistant_message: typeof result === 'string' ? result : '',
        input_tokens: 0,
        output_tokens: 0,
        tool_calls_made: 0,
        duration_ms: durationMs,
        stop_reason: stopReason,
      })
      return result
    } catch (err) {
      stopReason = 'error'
      const durationMs = Math.round(performance.now() - started)
      client.emit(ctx, {
        event_type: 'agent.turn.completed',
        assistant_message: '',
        input_tokens: 0,
        output_tokens: 0,
        tool_calls_made: 0,
        duration_ms: durationMs,
        stop_reason: stopReason,
      })
      throw err
    } finally {
      await client.flush().catch(() => undefined)
    }
  }
}
