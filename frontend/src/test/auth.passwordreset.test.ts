import { afterEach, describe, expect, it, vi } from 'vitest'
import { requestPasswordReset, resetPasswordConfirm } from '../api/auth'

const originalFetch = global.fetch

describe('auth password reset client', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    // @ts-expect-error reset in case
    global.fetch = originalFetch
    // reset cookie
    Object.defineProperty(document, 'cookie', { value: '', configurable: true })
  })

  it('requestPasswordReset: POSTs and returns void on 204', async () => {
    Object.defineProperty(document, 'cookie', { value: 'csrftoken=abc123', configurable: true })

    const spy = vi.spyOn(global, 'fetch' as any).mockResolvedValueOnce(
      new Response(null, { status: 204, headers: { 'Content-Type': 'application/json' } })
    )

    await expect(requestPasswordReset('alice@example.com')).resolves.toBeUndefined()

    expect(spy).toHaveBeenCalledTimes(1)
    const [url, init] = spy.mock.calls[0]
    expect(url).toMatch(/\/api\/v1\/auth\/password\/reset\/$/)
    expect(init.method).toBe('POST')
    // CSRF header is optional if cookie present; we set one in this test
    expect(new Headers(init.headers).get('X-CSRFToken')).toBe('abc123')
  })

  it('resetPasswordConfirm: POSTs and returns void on 204', async () => {
    Object.defineProperty(document, 'cookie', { value: 'csrftoken=zzz', configurable: true })

    const spy = vi.spyOn(global, 'fetch' as any).mockResolvedValueOnce(
      new Response(null, { status: 204, headers: { 'Content-Type': 'application/json' } })
    )

    await expect(
      resetPasswordConfirm({ uid: 'u', token: 't', newPassword1: 'A!2345678', newPassword2: 'A!2345678' })
    ).resolves.toBeUndefined()

    expect(spy).toHaveBeenCalledTimes(1)
    const [url, init] = spy.mock.calls[0]
    expect(url).toMatch(/\/api\/v1\/auth\/password\/reset\/confirm\/$/)
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('X-CSRFToken')).toBe('zzz')
  })

  it('propagates DRF error detail on 400', async () => {
    const body = JSON.stringify({ detail: 'Invalid or expired token.', code: 'invalid' })
    vi.spyOn(global, 'fetch' as any).mockResolvedValueOnce(
      new Response(body, { status: 400, headers: { 'Content-Type': 'application/json' } })
    )

    await expect(
      resetPasswordConfirm({ uid: 'u', token: 'bad', newPassword1: 'x', newPassword2: 'x' })
    ).rejects.toMatchObject({ status: 400, message: 'Invalid or expired token.' })
  })
})
