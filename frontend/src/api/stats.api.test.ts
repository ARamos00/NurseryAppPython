import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest'
import { getResourceCount, getCounts, HttpError } from '../api/stats'

function mockFetchOnce(payload: any, init?: { ok?: boolean; status?: number }) {
  const ok = init?.ok ?? true
  const status = init?.status ?? 200
  const res = {
    ok,
    status,
    json: async () => payload,
  } as any
  ;(globalThis as any).fetch = vi.fn().mockResolvedValue(res)
}

describe('stats api', () => {
  beforeEach(() => {
    vi.useRealTimers()
  })
  afterEach(() => {
    vi.resetAllMocks()
  })

  test('getResourceCount returns numeric count', async () => {
    mockFetchOnce({ count: 42 })
    const n = await getResourceCount('plants')
    expect(n).toBe(42)
  })

  test('getResourceCount throws HttpError on non-2xx', async () => {
    mockFetchOnce({ detail: 'nope' }, { ok: false, status: 403 })
    await expect(getResourceCount('plants')).rejects.toBeInstanceOf(HttpError)
  })

  test('getResourceCount throws on malformed payload', async () => {
    mockFetchOnce({ results: [] })
    await expect(getResourceCount('plants')).rejects.toBeInstanceOf(Error)
  })

  test('getCounts aggregates success and failure', async () => {
    // First success, second failure
    const sequence = [
      { ok: true, status: 200, payload: { count: 7 } },
      { ok: false, status: 500, payload: { detail: 'err' } },
    ]
    ;(globalThis as any).fetch = vi
      .fn()
      .mockResolvedValueOnce(makeRes(sequence[0]))
      .mockResolvedValueOnce(makeRes(sequence[1]))

    const out = await getCounts(['taxa', 'plants'])
    expect(out.taxa).toBe(7)
    expect(out.plants).toBeNull()
  })
})

function makeRes(x: { ok: boolean; status: number; payload: any }) {
  return {
    ok: x.ok,
    status: x.status,
    json: async () => x.payload,
  } as any
}
