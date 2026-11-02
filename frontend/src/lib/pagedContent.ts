import { computed, ref } from 'vue'
import type { RuleContent } from '../api/types'

export type PageFetcher = (q: string, offset: number, limit: number) => Promise<RuleContent>

export const RULE_PAGE_SIZE = 200

/**
 * 服务端分页 + 检索的规则内容列表。
 * - reset(q)：换规则或换检索词时从第一页重新加载
 * - loadMore()：滚动到底部时追加下一页；已在加载或已加载完则忽略
 * 每次 reset 递增序号，过期请求的结果直接丢弃，避免快速输入时旧结果覆盖新结果。
 */
export function usePagedContent(fetchPage: PageFetcher, pageSize = RULE_PAGE_SIZE) {
  const lines = ref<string[]>([])
  const total = ref(0)
  const matched = ref(0)
  const query = ref('')
  const loading = ref(false)
  const error = ref('')
  /** 第一页是否已返回（用于区分「加载中」和「没有结果」） */
  const ready = ref(false)
  const done = computed(() => ready.value && lines.value.length >= matched.value)

  let seq = 0

  async function fetchInto(mine: number, offset: number) {
    loading.value = true
    error.value = ''
    try {
      const page = await fetchPage(query.value, offset, pageSize)
      if (mine !== seq) return
      total.value = page.total
      matched.value = page.matched
      lines.value = offset === 0 ? page.lines : lines.value.concat(page.lines)
      ready.value = true
    } catch (e) {
      if (mine === seq) error.value = (e as Error).message
    } finally {
      if (mine === seq) loading.value = false
    }
  }

  function reset(q = '') {
    const mine = ++seq
    query.value = q.trim()
    lines.value = []
    matched.value = 0
    ready.value = false
    return fetchInto(mine, 0)
  }

  function loadMore() {
    if (loading.value || done.value || !ready.value || error.value) return Promise.resolve()
    return fetchInto(seq, lines.value.length)
  }

  /** 丢弃当前内容与进行中的请求（例如取消选择规则） */
  function clear() {
    seq++
    lines.value = []
    total.value = 0
    matched.value = 0
    query.value = ''
    loading.value = false
    error.value = ''
    ready.value = false
  }

  return { lines, total, matched, query, loading, error, ready, done, reset, loadMore, clear }
}
