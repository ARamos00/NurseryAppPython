/* Minimal stats client for DRF list endpoints.
   Strategy: GET /api/v1/<resource>/?page_size=1 and read `count` from the payload.
   Assumptions:
   - Session cookies are set (credentials: 'include').
   - CSRF is not required for safe (GET) requests.
*/

export class HttpError extends Error {
  status: number
  constructor(status: number, message?: string) {
    super(message ?? `HTTP ${status}`)
    this.status = status
  }
}

type CountPayload = { count: number }

/** Base path for the versioned API. Adjust if your frontend proxies, e.g., '/api/v1'. */
const API_BASE = '/api/v1'

type FetchOpts = { signal?: AbortSignal; timeoutMs?: number }

/** Fetch a single resource count from a DRF list endpoint. */
export async function getResourceCount(resource: string, opts: FetchOpts = {}): Promise<number> {
  const { signal, timeoutMs = 8000 } = opts
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)

  // Combine external signal with our timeout signal
  if (signal) {
    signal.addEventListener('abort', () => ctrl.abort(), { once: true })
  }

  const url = `${API_BASE}/${trimSlashes(resource)}/?page_size=1`

  try {
    const res = await fetch(url, {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' },
      signal: ctrl.signal,
    })
    if (!res.ok) {
      throw new HttpError(res.status, `Failed to load ${resource} count`)
    }
    const data = (await res.json()) as Partial<CountPayload>
    if (typeof data.count !== 'number') {
      throw new Error(`Malformed response for ${resource} (missing numeric 'count')`)
    }
    return data.count
  } catch (err) {
    // Normalize AbortError message
    if (isAbortError(err)) throw new Error(`Request timed out or aborted for ${resource}`)
    throw err
  } finally {
    clearTimeout(timer)
  }
}

/** Fetch multiple resource counts concurrently. */
export async function getCounts(
  resources: string[],
  opts: FetchOpts = {},
): Promise<Record<string, number | null>> {
  const results = await Promise.allSettled(resources.map((r) => getResourceCount(r, opts)))
  const out: Record<string, number | null> = {}
  resources.forEach((r, i) => {
    const res = results[i]
    out[r] = res.status === 'fulfilled' ? res.value : null
  })
  return out
}

// --------- helpers ---------
function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError'
}

function trimSlashes(s: string): string {
  return s.replace(/^\/+|\/+$/g, '')
}
