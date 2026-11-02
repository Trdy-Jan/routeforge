<script lang="ts">
import { ref } from 'vue'
import type { LibraryIndex } from '../api/types'

// 模块级缓存：同一页面会话内重开抽屉或切换页面不重复请求索引
const sharedIndex = ref<LibraryIndex | null>(null)
</script>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { NAlert, NButton, NEmpty, NInput, NSpin, NTab, NTabs, NVirtualList } from 'naive-ui'
import { api } from '../api'
import type { LibraryCategory, LibraryItem } from '../api/types'
import { formatTime } from '../lib/format'
import { usePagedContent } from '../lib/pagedContent'
import { LIBRARY_CATEGORIES, searchLibrary } from '../lib/ruleLibrary'

defineSlots<{ actions?: (props: { item: LibraryItem }) => unknown }>()

const category = ref<LibraryCategory>('geosite')
const query = ref('')
const loading = ref(false)
const loadError = ref('')
const selected = ref<LibraryItem | null>(null)
const lineFilter = ref('')

// 规则内容由服务端分页下发；筛选也在服务端完成，浏览器只持有已滚动到的部分
const LINE_HEIGHT = 24
const paged = usePagedContent((q, offset, limit) => {
  const item = selected.value
  if (!item) return Promise.reject(new Error('未选择规则'))
  return api.ruleContent(item.category, item.name, { q, offset, limit })
})
const lineItems = computed(() => paged.lines.value.map((l, i) => ({ key: i, l })))
// 刚选中规则、第一页尚未返回：整块显示加载状态；之后检索时保留筛选框，只在列表上显示加载
const firstLoad = ref(false)
watch(paged.ready, (r) => {
  if (r) firstLoad.value = false
})

const results = computed(() => (sharedIndex.value ? searchLibrary(sharedIndex.value.items, category.value, query.value) : []))

async function load(force = false) {
  loading.value = true
  loadError.value = ''
  try {
    sharedIndex.value = force ? await api.refreshRuleLibrary() : await api.ruleLibrary()
  } catch (e) {
    loadError.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (!sharedIndex.value) load()
})

let filterTimer: ReturnType<typeof setTimeout> | undefined

function select(item: LibraryItem) {
  clearTimeout(filterTimer)
  selected.value = item
  lineFilter.value = ''
  firstLoad.value = true
  paged.reset()
}

// 输入停顿 300ms 后再向服务端检索，避免每个字符都发请求
watch(lineFilter, (q) => {
  clearTimeout(filterTimer)
  if (!selected.value || q.trim() === paged.query.value) return
  filterTimer = setTimeout(() => paged.reset(q), 300)
})
onUnmounted(() => clearTimeout(filterTimer))

// 接近底部（剩余不足一屏）时加载下一页
function onLinesScroll(e: Event) {
  const el = e.target as HTMLElement
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - LINE_HEIGHT * 20) paged.loadMore()
}

watch(category, () => {
  clearTimeout(filterTimer)
  selected.value = null
  lineFilter.value = ''
  paged.clear()
})
</script>

<template>
  <div class="rl">
    <div class="rl__bar">
      <NTabs v-model:value="category" type="segment" size="small" class="rl__tabs">
        <NTab v-for="c in LIBRARY_CATEGORIES" :key="c.value" :name="c.value">{{ c.label }}</NTab>
      </NTabs>
      <NInput v-model:value="query" clearable placeholder="搜索规则名，如 openai、netflix、cn" class="rl__search" />
      <span v-if="sharedIndex?.updated_at" class="rl__meta">更新于 {{ formatTime(sharedIndex.updated_at) }}</span>
      <NButton size="small" :loading="loading" @click="load(true)">刷新</NButton>
    </div>

    <NAlert v-if="sharedIndex?.error" type="warning" :show-icon="false" class="rl__notice">
      {{ sharedIndex.error }}（当前显示的是上次成功获取的列表）
    </NAlert>

    <div v-if="!sharedIndex" class="rl__state">
      <NSpin v-if="loading" />
      <div v-else-if="loadError" class="rl__error">
        <p>{{ loadError }}</p>
        <NButton size="small" @click="load()">重试</NButton>
      </div>
    </div>

    <div v-else class="rl__body">
      <div class="rl__list">
        <div class="rl__count">{{ results.length }} 条结果</div>
        <NEmpty v-if="!results.length" description="没有匹配的规则" class="rl__empty" />
        <NVirtualList v-else :items="results" :item-size="32" key-field="name" class="rl__vlist">
          <template #default="{ item }">
            <button
              type="button"
              class="rl__item mono"
              :class="{ 'rl__item--active': selected?.name === item.name && selected?.category === item.category }"
              @click="select(item)"
            >
              {{ item.name }}
            </button>
          </template>
        </NVirtualList>
      </div>

      <div class="rl__preview">
        <div v-if="!selected" class="rl__hint">选择一条规则，查看它包含的域名或 IP 段。</div>
        <template v-else>
          <div class="rl__head">
            <span class="rl__cat">{{ selected.category }}</span>
            <span class="rl__name mono">{{ selected.name }}</span>
          </div>
          <div class="rl__url mono">{{ selected.url }}</div>
          <div v-if="$slots.actions" class="rl__actions"><slot name="actions" :item="selected" /></div>
          <!-- 首次加载出错（还没有任何内容）：给出重试 -->
          <div v-if="firstLoad && paged.error.value" class="rl__error">
            <p>{{ paged.error.value }}</p>
            <NButton size="small" @click="paged.reset(lineFilter)">重试</NButton>
          </div>
          <NSpin v-else-if="firstLoad" size="small" class="rl__state" />
          <template v-else>
            <div class="rl__content-bar">
              <span class="rl__meta">
                <template v-if="paged.query.value">
                  匹配 <span class="mono">{{ paged.matched.value }}</span> /
                </template>
                共 <span class="mono">{{ paged.total.value }}</span> 条
              </span>
              <NInput
                v-model:value="lineFilter"
                size="small"
                clearable
                placeholder="在全部条目中检索"
                class="rl__filter"
              />
            </div>
            <NSpin :show="paged.loading.value && !paged.lines.value.length" size="small">
              <p v-if="paged.error.value && !paged.lines.value.length" class="rl__error">{{ paged.error.value }}</p>
              <NEmpty
                v-else-if="paged.ready.value && !paged.matched.value"
                description="没有匹配的条目"
                class="rl__empty"
              />
              <NVirtualList
                v-else
                :items="lineItems"
                :item-size="LINE_HEIGHT"
                class="rl__lines"
                @scroll="onLinesScroll"
              >
                <template #default="{ item }">
                  <div class="rl__line mono">{{ item.l }}</div>
                </template>
              </NVirtualList>
            </NSpin>
            <div v-if="paged.ready.value && paged.matched.value" class="rl__progress">
              <template v-if="paged.error.value">
                加载失败：{{ paged.error.value }}
                <NButton text type="primary" size="tiny" @click="paged.reset(lineFilter)">重试</NButton>
              </template>
              <template v-else-if="paged.loading.value">正在加载更多…</template>
              <template v-else-if="!paged.done.value">
                已加载 <span class="mono">{{ paged.lines.value.length }}</span> 条，滚动到底部继续加载
              </template>
              <template v-else>已全部加载</template>
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rl {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.rl__bar {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.rl__tabs {
  width: 260px;
}
.rl__search {
  flex: 1 1 220px;
  min-width: 0;
}
.rl__meta,
.rl__count,
.rl__hint {
  color: var(--rf-muted);
  font-size: 13px;
}
.rl__body {
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(200px, 2fr) minmax(0, 3fr);
}
.rl__list,
.rl__preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.rl__vlist {
  border: 1px solid var(--rf-line);
  border-radius: 6px;
  height: 460px;
}
.rl__item {
  background: none;
  border: 0;
  color: var(--rf-text);
  cursor: pointer;
  display: block;
  font-size: 13px;
  height: 32px;
  overflow: hidden;
  padding: 0 10px;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
}
.rl__item:hover {
  background: var(--rf-line-soft);
}
.rl__item--active,
.rl__item--active:hover {
  background: var(--rf-tint);
  color: var(--rf-primary);
  font-weight: 600;
}
.rl__head {
  align-items: baseline;
  display: flex;
  gap: 8px;
}
.rl__cat {
  border: 1px solid var(--rf-line);
  border-radius: 4px;
  color: var(--rf-muted);
  font-size: 12px;
  padding: 0 6px;
}
.rl__name {
  font-size: 16px;
  font-weight: 600;
  word-break: break-all;
}
.rl__url {
  color: var(--rf-muted);
  font-size: 12px;
  user-select: all;
  word-break: break-all;
}
.rl__actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.rl__content-bar {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: space-between;
}
.rl__filter {
  max-width: 220px;
}
.rl__progress {
  color: var(--rf-faint);
  font-size: 12px;
}
.rl__lines {
  border: 1px solid var(--rf-line);
  border-radius: 6px;
  height: 340px;
}
.rl__line {
  font-size: 12px;
  height: 24px;
  line-height: 24px;
  overflow: hidden;
  padding: 0 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rl__state {
  display: flex;
  justify-content: center;
  padding: 32px 0;
}
.rl__error {
  color: var(--rf-error);
  font-size: 13px;
  text-align: center;
}
.rl__empty {
  padding: 24px 0;
}
@media (max-width: 768px) {
  .rl__body {
    grid-template-columns: 1fr;
  }
  .rl__vlist {
    height: 260px;
  }
}
</style>
