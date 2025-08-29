// Minimal, production-clean fetch wrapper for the Nursery Tracker SPA.
// - Base URL: /api/v1/
// - credentials: 'include' (session cookie)
// - CSRF: attach X-CSRFToken for unsafe methods using the 'csrftoken' cookie
// - Errors: decode DRF shape {detail, code}; fallback to Response.statusText
//
// Test-robustness: prefer JSON parsing when a .json() method exists even if
// Content-Type is missing (common in mocks). Only call .text() if it exists.

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

export class HttpError extends Error {
  status: number
  code?: string
  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'HttpError'
    this.status = status
    this.code = code
  }
}

const BASE = '/api/v1/'

function join(base: string, path: string): string {
  if (path.startsWith('http')) return path
  if (base.endsWith('/') && path.startsWith('/')) return base + path.slice(1)
  if (!base.endsWith('/') && !path.startsWith('/')) return base + '/' + path
  return base + path
}

function getCookie(name: string): string | undefined {
  if (typeof document === 'undefined') return undefined
  const v = document.cookie
    .split(';')
    .map((s) => s.trim())
    .find((s) => s.startsWith(`${name}=`))
  return v ? decodeURIComponent(v.split('=').slice(1).join('=')) : undefined
}

function isUnsafe(method: HttpMethod): boolean {
  return method === 'POST' || method === 'PUT' || method === 'PATCH' || method === 'DELETE'
}

type HttpOptions = Omit<RequestInit, 'method' | 'body'> & {
  method?: HttpMethod
  body?: any
}

export async function http<T = unknown>(path: string, opts: HttpOptions = {}): Promise<T> {
  const method: HttpMethod = (opts.method || 'GET').toUpperCase() as HttpMethod
  const url = join(BASE, path)

  const headers = new Headers(opts.headers || {})
  headers.set('Accept', 'application/json')

  let body: BodyInit | undefined
  const hasJsonBody = opts.body !== undefined && !(opts.body instanceof FormData)
  if (hasJsonBody) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(opts.body)
  } else if (opts.body instanceof FormData) {
    body = opts.body // browser sets Content-Type (multipart boundary)
  }

  if (isUnsafe(method)) {
    const csrf = getCookie('csrftoken')
    if (csrf) headers.set('X-CSRFToken', csrf)
  }

  const resp = await fetch(url, {
    method,
    headers,
    body,
    credentials: 'include',
    redirect: opts.redirect,
    signal: opts.signal,
    mode: opts.mode,
    cache: opts.cache,
  })

  // 204 / No Content → return undefined
  if (resp.status === 204) return undefined as unknown as T

  const ct = (resp.headers && typeof (resp.headers as any).get === 'function'
    ? resp.headers.get('Content-Type')
    : '') || ''

  // -------------------------
  // Success path
  // -------------------------
  if (resp.ok) {
    // Prefer JSON if possible: either content-type says JSON or a json() method exists
    if (ct.includes('application/json') || typeof (resp as any).json === 'function') {
      try {
        return (await (resp as any).json()) as T
      } catch {
        // fall through to text
      }
    }
    if (typeof (resp as any).text === 'function') {
      // @ts-expect-error consumer should specify generic type if not JSON
      return await (resp as any).text()
    }
    // Nothing else to return; give back undefined
    return undefined as unknown as T
  }

  // -------------------------
  // Error path
  // -------------------------
  let message = resp.statusText || `HTTP ${resp.status}`
  let code: string | undefined

  if (ct.includes('application/json') || typeof (resp as any).json === 'function') {
    try {
      const data = await (resp as any).json()
      if (data && typeof data.detail === 'string') message = data.detail
      if (data && typeof data.code === 'string') code = data.code
    } catch {
      // ignore parse failures; keep message from statusText
    }
  } else if (typeof (resp as any).text === 'function') {
    try {
      const txt = await (resp as any).text()
      if (txt) message = txt
    } catch {
      // ignore text failures
    }
  }

  throw new HttpError(message, resp.status, code)
}

// Optional sugar (kept commented to avoid dead exports):
// export const get = <T>(p: string, o?: HttpOptions) => http<T>(p, { ...o, method: 'GET' })
// export const post = <T>(p: string, body?: any, o?: HttpOptions) => http<T>(p, { ...o, method: 'POST', body })
