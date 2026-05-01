import { describe, expect, it, vi } from 'vitest'
import { GoderashClient } from './client.js'

describe('GoderashClient', () => {
  it('buffers events until flush', () => {
    const client = new GoderashClient({
      apiKey: 'gdr_t',
      tenant: 't',
      batchSize: 100,
      fetchImpl: vi.fn() as unknown as typeof fetch,
    })
    const ctx = client.newContext()
    client.emit(ctx, { event_type: 'agent.turn.started', user_message: 'hi' })
    expect(client._getBuffer().length).toBe(1)
  })

  it('flushes when batch size reached', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 202 })) as unknown as typeof fetch

    const client = new GoderashClient({
      apiKey: 'gdr_t',
      tenant: 't',
      batchSize: 2,
      fetchImpl: fetchMock,
    })
    const ctx = client.newContext()
    client.emit(ctx, { event_type: 'agent.turn.started', user_message: '1' })
    client.emit(ctx, { event_type: 'agent.turn.started', user_message: '2' })

    await new Promise((r) => setTimeout(r, 0))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('rejects missing api key', () => {
    expect(
      () =>
        new GoderashClient({ apiKey: '', tenant: 't', fetchImpl: vi.fn() as unknown as typeof fetch }),
    ).toThrow()
  })
})
