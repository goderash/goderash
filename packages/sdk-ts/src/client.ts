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

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.timeoutMs)

    try {
      const res = await this.fetchImpl(`${this.endpoint}/v1/events`, {
        method: 'POST',
        signal: controller.signal,
        headers: {
          'content-type': 'application/json',
          'x-goderash-api-key': this.apiKey,
          'x-goderash-tenant': this.tenant,
        },
        body: JSON.stringify({ events: batch }),
      })
      if (!res.ok) {
        const body = await res.text().catch(() => '')
        throw new Error(`goderash ingest ${res.status}: ${body.slice(0, 300)}`)
      }
    } finally {
      clearTimeout(timer)
    }
  }

  /** For tests: expose the current buffer without mutating it. */
  _getBuffer(): ReadonlyArray<GoderashEvent> {
    return this.buffer
  }
}
