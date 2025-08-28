import { afterEach, describe, expect, it, vi } from 'vitest'
import { getCsrf, login, logout, me, type User } from './auth'

// Utility to mock a single fetch call with a canned response
function mockFetchOnce(res: Partial<Response> & { json?: any; headersInit?: Record<string, string> }) {
  const headers = new Headers(res.headersInit ?? {})
  const ok = res.ok ?? true
  const status = res.status ?? 200
  const statusText = res.statusText ?? 'OK'
  const json = res.json ?? {}
  vi.spyOn(global, 'fetch').mockResolvedValueOnce({
    ok,
    status,
    statusText,
    headers,
    json: async () => json
  } as Response)
}

describe('auth client', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    // reset cookies between tests
    document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
  })

  it('getCsrf stores token from header', async () => {
    mockFetchOnce({ ok: true, status: 204, headersInit: { 'X-CSRFToken': 'abc123' } })
    await expect(getCsrf()).resolves.toBeUndefined()
  })

  it('login success returns user', async () => {
    const u: User = { id: 1, username: 'alice', email: 'a@example.com' }
    mockFetchOnce({ json: u })
    await expect(login('alice', 'pw')).resolves.toEqual(u)
  })

  it('me 401 surfaces error', async () => {
    mockFetchOnce({ ok: false, status: 401, statusText: 'Unauthorized', json: { detail: 'No', code: 'not_auth' } })
    await expect(me()).rejects.toMatchObject({ status: 401 })
  })

  it('logout returns void', async () => {
    mockFetchOnce({ status: 204 })
    await expect(logout()).resolves.toBeUndefined()
  })

  it('uses cookie CSRF token over memory when they differ', async () => {
    // First, set a "stale" memory token via getCsrf header
    mockFetchOnce({ ok: true, status: 204, headersInit: { 'X-CSRFToken': 'OLD_TOKEN' } })
    await getCsrf()

    // Now simulate Django rotated CSRF cookie after login
    document.cookie = 'csrftoken=NEW_TOKEN; path=/'

    // Intercept the POST and assert header uses NEW_TOKEN
    const fetchSpy = vi.spyOn(global, 'fetch')
    fetchSpy.mockImplementationOnce(async (input: RequestInfo | URL, init?: RequestInit) => {
      const h = new Headers(init?.headers as HeadersInit)
      expect(h.get('X-CSRFToken')).toBe('NEW_TOKEN')
      return {
        ok: true,
        status: 204,
        headers: new Headers(),
        json: async () => ({})
      } as Response
    })

    await expect(logout()).resolves.toBeUndefined()
  })
})
