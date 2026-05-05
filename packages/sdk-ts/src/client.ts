/**
 * GoderashClient — buffers events and flushes batches to the control plane.
 */

import type { GoderashEvent, GoderashEventPayload } from './events/types.js'

export interface GoderashContext {
  tenantId: string
  agentId: string
  conversationId: string
  turnId: string
  parentEventId?: string
}

export interface GoderashClientOptions {
  apiKey: string
  tenant: string
  agentId?: string
  endpoint?: string
  batchSize?: number
  timeoutMs?: number
  fetchImpl?: typeof fetch
}

const RETRY_MAX = 3
const RETRY_BASE_MS = 500
const RETRY_CAP_MS = 10_000
const RETRYABLE_STATUSES = new Set([429, 500, 502, 503, 504])

export class GoderashClient {
  private readonly apiKey: string
  private readonly tenant: string
  private readonly agentId: string
  private readonly endpoint: string
  private readonly batchSize: number
  private readonly timeoutMs: number
  private readonly fetchImpl: typeof fetch

  private buffer: GoderashEvent[] = []

  constructor(opts: GoderashClientOptions) {
    if (!opts.apiKey) throw new Error('GoderashClient requires apiKey')
    if (!opts.tenant) throw new Error('GoderashClient requires tenant')

    this.apiKey = opts.apiKey
    this.tenant = opts.tenant
    this.agentId = opts.agentId ?? 'default'
    this.endpoint = (opts.endpoint ?? 'http://localhost:8000').replace(/\/$/, '')
    this.batchSize = opts.batchSize ?? 50
    this.timeoutMs = opts.timeoutMs ?? 5000
    this.fetchImpl = opts.fetchImpl ?? globalThis.fetch
  }

  newContext(overrides?: Partial<GoderashContext>): GoderashContext {
    return {
      tenantId: this.tenant,
      agentId: this.agentId,
      conversationId: overrides?.conversationId ?? crypto.randomUUID(),
      turnId: overrides?.turnId ?? crypto.randomUUID(),
      parentEventId: overrides?.parentEventId,
    }
  }

  emit(ctx: GoderashContext, payload: GoderashEventPayload): void {
    const event: GoderashEvent = {
      event_id: crypto.randomUUID(),
      tenant_id: ctx.tenantId,
      agent_id: ctx.agentId,
      conversation_id: ctx.conversationId,
      turn_id: ctx.turnId,
      parent_event_id: ctx.parentEventId ?? null,
      schema_version: 1,
      occurred_at: new Date().toISOString(),
      payload,
    }
    this.buffer.push(event)

    if (this.buffer.length >= this.batchSize) {
      void this.flush().catch((err) => {
        console.error('[goderash] flush failed', err)
      })
    }
  }

  async flush(): Promise<void> {
    if (this.buffer.length === 0) return
    const batch = this.buffer
    this.buffer = []

    // Serialize once; same bytes on every retry (idempotent — server dedupes by event_id).
    const body = JSON.stringify({ events: batch })
    let lastError: Error | undefined

    for (let attempt = 0; attempt <= RETRY_MAX; attempt++) {
      if (attempt > 0) {
        await this._sleep(this._jitterDelay(attempt - 1))
      }

      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), this.timeoutMs)

      let res: Response | undefined
      let fetchError: Error | undefined

      try {
        res = await this.fetchImpl(`${this.endpoint}/v1/events`, {
          method: 'POST',
          signal: controller.signal,
          headers: {
            'content-type': 'application/json',
            'x-goderash-api-key': this.apiKey,
            'x-goderash-tenant': this.tenant,
          },
          body,
        })
      } catch (err) {
        fetchError = err instanceof Error ? err : new Error(String(err))
      } finally {
        clearTimeout(timer)
      }

      if (fetchError) {
        lastError = fetchError
        continue
      }

      if (res!.ok) return

      const text = await res!.text().catch(() => '')
      const err = new Error(`goderash ingest ${res!.status}: ${text.slice(0, 300)}`)

      if (!RETRYABLE_STATUSES.has(res!.status)) throw err

      lastError = err
    }

    throw lastError ?? new Error('goderash: flush failed after retries')
  }

  private _jitterDelay(attempt: number): number {
    const ceiling = Math.min(RETRY_BASE_MS * Math.pow(2, attempt), RETRY_CAP_MS)
    return Math.random() * ceiling
  }

  private _sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }

  /** For tests: expose the current buffer without mutating it. */
  _getBuffer(): ReadonlyArray<GoderashEvent> {
    return this.buffer
  }
}
