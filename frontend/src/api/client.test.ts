import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request, setUnauthorizedHandler } from './client'

function mockFetch(status: number, body?: unknown) {
  const fn = vi.fn(async (_url: string, _init?: RequestInit) =>
    new Response(body === undefined ? null : JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

describe('request', () => {
  it('sends JSON with content type on POST', async () => {
    const fn = mockFetch(200, { ok: true })
    expect(await request('POST', '/api/x', { a: 1 })).toEqual({ ok: true })
    const init = fn.mock.calls[0][1]!
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{"a":1}')
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('sends {} when a write has no body', async () => {
    const fn = mockFetch(200, {})
    await request('POST', '/api/x')
    expect(fn.mock.calls[0][1]!.body).toBe('{}')
  })

  it('sends no body on GET and DELETE', async () => {
    const fn = mockFetch(200, [])
    await request('GET', '/api/x')
    expect(fn.mock.calls[0][1]!.body).toBeUndefined()
  })

  it('returns undefined for 204', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
    expect(await request('DELETE', '/api/x/1')).toBeUndefined()
  })

  it('uses string detail as error message', async () => {
    mockFetch(400, { detail: '手动节点源无需刷新' })
    await expect(request('POST', '/api/x')).rejects.toMatchObject({ status: 400, message: '手动节点源无需刷新' })
  })

  it('joins 422 validation messages', async () => {
    mockFetch(422, { detail: [{ msg: 'Value error, 订阅源需要 http(s) 链接' }, { msg: 'Field required' }] })
    await expect(request('POST', '/api/x')).rejects.toThrow('Value error, 订阅源需要 http(s) 链接；Field required')
  })

  it('falls back to status text when body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('oops', { status: 502 })))
    await expect(request('GET', '/api/x')).rejects.toThrow('请求失败（HTTP 502）')
  })

  it('calls the unauthorized handler on 401', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    mockFetch(401, { detail: '未登录' })
    await expect(request('GET', '/api/x')).rejects.toBeInstanceOf(ApiError)
    expect(handler).toHaveBeenCalledOnce()
  })
})
