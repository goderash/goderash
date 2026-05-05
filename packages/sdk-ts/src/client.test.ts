import { describe, expect, it, vi } from 'vitest'
import { GoderashClient } from './client.js'

function makeClient(fetchMock: typeof fetch, batchSize = 1000) {
  return new GoderashClient({ apiKey: 'gdr_t', tenant: 't', batchSize, fetchImpl: fetchMock })
}

function emitOne(client: GoderashClient) {
  client.emit(client.newContext(), { event_type: 'agent.turn.started', user_message: 'hi' })
}

describe('GoderashClient', () => {
  it('buffers events until flush', () => {
    const client = makeClient(vi.fn() as unknown as typeof fetch, 100)
    client.emit(client.newContext(), { event_type: 'agent.turn.started', user_message: 'hi' })
    expect(client._getBuffer().length).toBe(1)
  })

  it('flushes when batch size reached', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 202 })) as unknown as typeof fetch
    const client = makeClient(fetchMock, 2)
    const ctx = client.newContext()
    client.emit(ctx, { event_type: 'agent.turn.started', user_message: '1' })
    client.emit(ctx, { event_type: 'agent.turn.started', user_message: '2' })
    await new Promise((r) => setTimeout(r, 0))
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('rejects missing api key', () => {
    expect(
      () => new GoderashClient({ apiKey: '', tenant: 't', fetchImpl: vi.fn() as unknown as typeof fetch }),
    ).toThrow()
  })
})

describe('retry logic', () => {
  function noSleep(client: GoderashClient) {
    vi.spyOn(client as unknown as { _sleep: (ms: number) => Promise<void> }, '_sleep')
      .mockResolvedValue(undefined)
  }

  it('succeeds without retrying when server returns 202', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 202 })) as unknown as typeof fetch
    const client = makeClient(fetchMock)
    noSleep(client)
    emitOne(client)
    await client.flush()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('retries on 503 and succeeds on second attempt', async () => {
    let calls = 0
    const fetchMock = vi.fn().mockImplementation(async () => {
      calls++
      return calls === 1
        ? new Response('down', { status: 503 })
        : new Response(null, { status: 202 })
    }) as unknown as typeof fetch
    const client = makeClient(fetchMock)
    noSleep(client)
    emitOne(client)
    await client.flush()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('exhausts all retries and rejects on persistent 503', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('down', { status: 503 })) as unknown as typeof fetch
    const client = makeClient(fetchMock)
    noSleep(client)
    emitOne(client)
    await expect(client.flush()).rejects.toThrow('503')
    expect(fetchMock).toHaveBeenCalledTimes(4) // 1 initial + 3 retries
  })

  it('does not retry on 400', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('bad request', { status: 400 })) as unknown as typeof fetch
    const client = makeClient(fetchMock)
    noSleep(client)
    emitOne(client)
    await expect(client.flush()).rejects.toThrow('400')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('retries on network error and succeeds on second attempt', async () => {
    let calls = 0
    const fetchMock = vi.fn().mockImplementation(async () => {
      calls++
      if (calls === 1) throw new TypeError('Failed to fetch')
      return new Response(null, { status: 202 })
    }) as unknown as typeof fetch
    const client = makeClient(fetchMock)
    noSleep(client)
    emitOne(client)
    await client.flush()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('retries on 429 and succeeds', async () => {
    let calls = 0
    const fetchMock = vi.fn().mockImplementation(async () => {
      calls++
      return calls === 1
        ? new Response('slow down', { status: 429 })
        : new Response(null, { status: 202 })
    }) as unknown as typeof fetch
    const client = makeClient(fetchMock)
    noSleep(client)
    emitOne(client)
    await client.flush()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
