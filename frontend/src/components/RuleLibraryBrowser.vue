<script lang="ts">
import { ref } from 'vue'
import type { LibraryIndex } from '../api/types'

// 模块级缓存：同一页面会话内重开抽屉或切换页面不重复请求索引
const sharedIndex = ref<LibraryIndex | null>(null)
</script>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { NAlert, NButton, NEmpty, NInput, NSpin, NTab, NTabs, NVirtualList } from 'naive-ui'
import { api } from '../api'
import type { LibraryCategory, LibraryItem, RuleContent } from '../api/types'
import { formatTime } from '../lib/format'
import { LIBRARY_CATEGORIES, searchLibrary } from '../lib/ruleLibrary'

defineSlots<{ actions?: (props: { item: LibraryItem }) => unknown }>()

const category = ref<LibraryCategory>('geosite')
const query = ref('')
const loading = ref(false)
const loadError = ref('')
const selected = ref<LibraryItem | null>(null)
const content = ref<RuleContent | null>(null)
const contentLoading = ref(false)
const contentError = ref('')
const lineFilter = ref('')

const results = computed(() => (sharedIndex.value ? searchLibrary(sharedIndex.value.items, category.value, query.value) : []))
const filteredLines = computed(() => {
  const lines = content.value?.lines ?? []
  const q = lineFilter.value.trim().toLowerCase()
  return q ? lines.filter((l) => l.toLowerCase().includes(q)) : lines
})

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

async function select(item: LibraryItem) {
  selected.value = item
  content.value = null
  contentError.value = ''
  lineFilter.value = ''
  contentLoading.value = true
  try {
    const result = await api.ruleContent(item.category, item.name)
    if (selected.value === item) content.value = result
  } catch (e) {
    if (selected.value === item) contentError.value = (e as Error).message
  } finally {
    if (selected.value === item) contentLoading.value = false
  }
}

watch(category, () => {
  selected.value = null
  content.value = null
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
        <div v-if="!selected" class="rl__hint">在左侧选择一条规则，查看它包含的域名或 IP 段。</div>
        <template v-else>
          <div class="rl__head">
            <span class="rl__cat">{{ selected.category }}</span>
            <span class="rl__name mono">{{ selected.name }}</span>
          </div>
          <div class="rl__url mono">{{ selected.url }}</div>
          <div v-if="$slots.actions" class="rl__actions"><slot name="actions" :item="selected" /></div>
          <NSpin v-if="contentLoading" size="small" class="rl__state" />
          <p v-else-if="contentError" class="rl__error">{{ contentError }}</p>
          <template v-else-if="content">
            <div class="rl__content-bar">
              <span class="rl__meta">共 <span class="mono">{{ content.total }}</span> 条<template v-if="content.truncated">，仅显示前 {{ content.lines.length }} 条</template></span>
              <NInput v-model:value="lineFilter" size="small" clearable placeholder="在结果内筛选" class="rl__filter" />
            </div>
            <NEmpty v-if="!filteredLines.length" description="没有匹配的条目" class="rl__empty" />
            <NVirtualList v-else :items="filteredLines.map((l, i) => ({ key: i, l }))" :item-size="24" class="rl__lines">
              <template #default="{ item }">
                <div class="rl__line mono">{{ item.l }}</div>
              </template>
            </NVirtualList>
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
