export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(fn: (() => void) | null): void {
  onUnauthorized = fn
}

export async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: 'same-origin' }
  if (method !== 'GET' && method !== 'DELETE') {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body ?? {})
  }
  const resp = await fetch(path, init)
  if (resp.status === 401) onUnauthorized?.()
  if (!resp.ok) throw new ApiError(resp.status, await errorMessage(resp))
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

async function errorMessage(resp: Response): Promise<string> {
  try {
    const data = await resp.json()
    if (typeof data?.detail === 'string') return data.detail
    if (Array.isArray(data?.detail)) {
      return data.detail
        .map((d: unknown) => {
          const msg = (d as { msg?: unknown } | null)?.msg
          return (typeof msg === 'string' ? msg : String(d)).replace(/^Value error, /, '')
        })
        .join('；')
    }
  } catch {
    // 响应不是 JSON
  }
  return `请求失败（HTTP ${resp.status}）`
}
