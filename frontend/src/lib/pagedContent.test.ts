import { describe, expect, it } from 'vitest'
import type { RuleContent } from '../api/types'
import { usePagedContent } from './pagedContent'

const ALL = Array.from({ length: 7 }, (_, i) => `d${i}.com`)

function fakeServer(all = ALL) {
  const calls: Array<{ q: string; offset: number; limit: number }> = []
  const fetch = async (q: string, offset: number, limit: number): Promise<RuleContent> => {
    calls.push({ q, offset, limit })
    const matched = q ? all.filter((l) => l.includes(q)) : all
    return { total: all.length, matched: matched.length, offset, lines: matched.slice(offset, offset + limit) }
  }
  return { fetch, calls }
}

/** 可手动控制完成顺序的请求，用来模拟乱序返回 */
function deferredServer() {
  const pending: Array<{ q: string; resolve: (r: RuleContent) => void }> = []
  const fetch = (q: string) =>
    new Promise<RuleContent>((resolve) => pending.push({ q, resolve }))
  const respond = (i: number, lines: string[]) =>
    pending[i].resolve({ total: 10, matched: lines.length, offset: 0, lines })
  return { fetch, respond }
}

describe('usePagedContent', () => {
  it('loads the first page and appends further pages until done', async () => {
    const { fetch, calls } = fakeServer()
    const p = usePagedContent(fetch, 3)
    await p.reset()
    expect(p.lines.value).toEqual(['d0.com', 'd1.com', 'd2.com'])
    expect([p.total.value, p.matched.value, p.done.value]).toEqual([7, 7, false])

    await p.loadMore()
    await p.loadMore()
    expect(p.lines.value).toEqual(ALL)
    expect(p.done.value).toBe(true)

    await p.loadMore() // 已加载完：不再请求
    expect(calls.map((c) => c.offset)).toEqual([0, 3, 6])
  })

  it('passes the trimmed query and restarts from offset 0', async () => {
    const { fetch, calls } = fakeServer()
    const p = usePagedContent(fetch, 3)
    await p.reset()
    await p.loadMore()
    await p.reset('  d1 ')
    expect(calls.at(-1)).toEqual({ q: 'd1', offset: 0, limit: 3 })
    expect(p.lines.value).toEqual(['d1.com'])
    expect([p.total.value, p.matched.value, p.done.value]).toEqual([7, 1, true])
  })

  it('ignores loadMore while a request is in flight', async () => {
    const { fetch, calls } = fakeServer()
    const p = usePagedContent(fetch, 3)
    await p.reset()
    const a = p.loadMore()
    const b = p.loadMore()
    await Promise.all([a, b])
    expect(calls.map((c) => c.offset)).toEqual([0, 3])
  })

  it('drops stale responses when the query changes quickly', async () => {
    const s = deferredServer()
    const p = usePagedContent(s.fetch, 3)
    const first = p.reset('a')
    const second = p.reset('ab')
    s.respond(1, ['ab.com'])
    await second
    s.respond(0, ['a.com', 'xa.com']) // 旧请求后返回，不能覆盖
    await first
    expect(p.lines.value).toEqual(['ab.com'])
    expect(p.query.value).toBe('ab')
    expect(p.loading.value).toBe(false)
  })

  it('records errors and blocks loadMore until reset', async () => {
    let fail = true
    const p = usePagedContent(async () => {
      if (fail) throw new Error('上游失败')
      return { total: 1, matched: 1, offset: 0, lines: ['x'] }
    })
    await p.reset()
    expect(p.error.value).toBe('上游失败')
    expect(p.ready.value).toBe(false)
    fail = false
    await p.loadMore()
    expect(p.lines.value).toEqual([])
    await p.reset()
    expect(p.lines.value).toEqual(['x'])
    expect(p.error.value).toBe('')
  })

  it('clear discards in-flight results', async () => {
    const s = deferredServer()
    const p = usePagedContent(s.fetch, 3)
    const pending = p.reset()
    p.clear()
    s.respond(0, ['late.com'])
    await pending
    expect(p.lines.value).toEqual([])
    expect(p.ready.value).toBe(false)
  })
})
