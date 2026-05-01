/**
 * @goderash/adapter-openai-assistants — audit OpenAI Assistants runs.
 *
 * Walks `runs.steps.list` for a completed run and emits one Goderash
 * `tool.invoked` (and matching `tool.completed`) per tool call. Mirrors the
 * Python adapter under `python/goderash_adapter_openai/`.
 */

import { createHash } from 'node:crypto'
import type { GoderashClient, GoderashContext } from '@goderash/sdk'

type AnyDict = Record<string, unknown>

interface RunStepsAPI {
  list: (
    args: { thread_id: string; run_id: string; order?: 'asc' | 'desc'; limit?: number },
  ) => Promise<{ data?: AnyDict[] }> | { data?: AnyDict[] }
}

interface RunsAPI {
  steps: RunStepsAPI
}

interface ThreadsAPI {
  runs: RunsAPI
}

interface BetaAPI {
  threads: ThreadsAPI
}

interface OpenAILike {
  beta: BetaAPI
}

export interface AuditAssistantsRunOptions {
  client: OpenAILike
  goderash: GoderashClient
  context: GoderashContext
  run: AnyDict
  threadId: string
}

/**
 * Read all steps for a completed Assistants run and emit tool events.
 *
 * Call this after `runs.createAndPoll` returns a terminal status, or after
 * `runs.retrieve` reports `completed`/`failed`/`cancelled`.
 */
export async function auditAssistantsRun(opts: AuditAssistantsRunOptions): Promise<void> {
  const { client, goderash, context, run, threadId } = opts
  const runId = String(run.id)

  const stepsResp = await client.beta.threads.runs.steps.list({
    thread_id: threadId,
    run_id: runId,
    order: 'asc',
    limit: 100,
  })

  const steps = Array.isArray(stepsResp?.data) ? (stepsResp.data as AnyDict[]) : []

  for (const step of steps) {
    if (step.type !== 'tool_calls') continue
    const details = (step.step_details as AnyDict | undefined) ?? {}
    const calls = Array.isArray(details.tool_calls) ? (details.tool_calls as AnyDict[]) : []

    for (const call of calls) {
      const toolType = String(call.type ?? 'function')

      if (toolType === 'function') {
        const fn = (call.function as AnyDict | undefined) ?? {}
        const toolName = String(fn.name ?? 'unknown')
        const args = fn.arguments ?? ''
        const output = fn.output

        goderash.emit(context, {
          event_type: 'tool.invoked',
          tool_name: toolName,
          tool_category: 'query',
          input_args_hash: sha256Hex(args),
        })

        if (output != null) {
          goderash.emit(context, {
            event_type: 'tool.completed',
            tool_name: toolName,
            success: true,
            duration_ms: 0,
            result_hash: sha256Hex(output),
          })
        }
      } else if (
        toolType === 'code_interpreter' ||
        toolType === 'file_search' ||
        toolType === 'retrieval'
      ) {
        const ref = String(call.id ?? '')
        goderash.emit(context, {
          event_type: 'tool.invoked',
          tool_name: toolType,
          tool_category: 'intelligence',
          input_args_hash: sha256Hex(ref),
        })
        goderash.emit(context, {
          event_type: 'tool.completed',
          tool_name: toolType,
          success: true,
          duration_ms: 0,
          result_hash: sha256Hex(ref),
        })
      }
    }
  }

  if (run.status === 'failed') {
    const lastError = (run.last_error as AnyDict | undefined) ?? {}
    goderash.emit(context, {
      event_type: 'tool.failed',
      tool_name: 'assistants_run',
      error_class: String(lastError.code ?? 'unknown'),
      error_message: String(lastError.message ?? 'unknown').slice(0, 1024),
      duration_ms: 0,
    })
  }
}

// ---- helpers --------------------------------------------------------------

function sha256Hex(value: unknown): string {
  const blob = typeof value === 'string' ? value : JSON.stringify(value ?? null)
  return createHash('sha256').update(blob).digest('hex')
}
