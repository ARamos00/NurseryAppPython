// Fetch wrapper with cookie-based session + CSRF header support
const API_BASE = '/api/v1/'

let csrfTokenMemory: string | null = null

function setCsrfToken(token: string | null) {
  csrfTokenMemory = token
}

function readCookie(name: string): string | null {
  const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)')
  return m ? decodeURIComponent(m.pop() as string) : null
}

/**
 * Prime the CSRF cookie/token from the server.
 * - Always uses same-origin credentials.
 * - Captures the token from the X-CSRFToken response header (works even if cookie is HttpOnly).
 */
async function primeCsrf(): Promise<string | null> {
  const res = await fetch(API_BASE + 'auth/csrf/', { method: 'GET', credentials: 'include' })
  const headerToken = res.headers.get('X-CSRFToken')
  if (headerToken) setCsrfToken(headerToken)
  return headerToken
}

export async function http<T>(
  path: string,
  init: RequestInit & { unsafe?: boolean } = {}
): Promise<T> {
  const url = path.startsWith('http') ? path : API_BASE + path.replace(/^\/+/, '')
  const { unsafe, headers, ...rest } = init

  const finalHeaders = new Headers(headers ?? {})
  // Always include cookies
  const opts: RequestInit = { credentials: 'include', ...rest, headers: finalHeaders }

  // Attach CSRF header for unsafe methods
  const method = (opts.method || 'GET').toUpperCase()
  const isUnsafe = unsafe ?? ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)
  if (isUnsafe) {
    // IMPORTANT: Prefer the *current cookie* token over any cached value.
    // This avoids stale-memory mismatches right after login (when Django rotates).
    let token = readCookie('csrftoken')
    if (!token) {
      // Fallback to any previously cached header token
      token = csrfTokenMemory
    }
    if (!token) {
      // Last resort: prime from server, then use it
      token = await primeCsrf()
    }
    if (token) {
      // Keep memory in sync with the latest token we chose to send
      setCsrfToken(token)
      finalHeaders.set('X-CSRFToken', token)
    }
  }

  const res = await fetch(url, opts)
  if (!res.ok) {
    let detail = res.statusText
    let code: string | undefined
    try {
      const data = await res.json()
      if (data && typeof data.detail === 'string') {
        detail = data.detail
        code = typeof data.code === 'string' ? data.code : undefined
      }
    } catch {
      // If CSRF failed, Django often returns HTML; JSON parse will fail. We fall back to statusText.
    }
    const err = new Error(detail) as Error & { status?: number; code?: string }
    err.status = res.status
    if (code) err.code = code
    throw err
  }
  // Handle empty responses (e.g., 204)
  if (res.status === 204) {
    // If server returns CSRF token in header, remember it (keeps memory fresh after rotates).
    const headerToken = res.headers.get('X-CSRFToken')
    if (headerToken) setCsrfToken(headerToken)
    // @ts-expect-error - void return acceptable
    return undefined
  }
  return (await res.json()) as T
}

export function rememberCsrf(token: string | null) {
  setCsrfToken(token)
}
