<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import {
  NButton, NDataTable, NEmpty, NInput, NInputGroup, NModal, NSelect, NSpace, NSwitch, NTag, useDialog, useMessage,
  type DataTableColumns, type DataTableRowKey,
} from 'naive-ui'
import { api } from '../api'
import type { NodeItem, Source } from '../api/types'
import PageHeader from '../components/PageHeader.vue'

const message = useMessage()
const dialog = useDialog()

const nodes = ref<NodeItem[]>([])
const sources = ref<Source[]>([])
const sourceFilter = ref<number | null>(null)
const keyword = ref('')
const checked = ref<DataTableRowKey[]>([])
const loading = ref(false)

const sourceMap = computed(() => new Map(sources.value.map((s) => [s.id, s])))
const sourceOptions = computed(() => sources.value.map((s) => ({ label: s.name, value: s.id })))
const isManual = (n: NodeItem) => sourceMap.value.get(n.source_id)?.kind === 'manual'

async function load() {
  loading.value = true
  try {
    const [srcs, list] = await Promise.all([
      api.listSources(),
      api.listNodes({ source_id: sourceFilter.value, q: keyword.value.trim() || undefined }),
    ])
    sources.value = srcs
    nodes.value = list
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(sourceFilter, load)

async function toggle(n: NodeItem, enabled: boolean) {
  try {
    const updated = await api.updateNode(n.id, { enabled })
    n.enabled = updated.enabled
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function bulk(enabled: boolean) {
  try {
    const r = await api.bulkNodes(checked.value.map(Number), enabled)
    message.success(`已${enabled ? '启用' : '停用'} ${r.updated} 个节点`)
    checked.value = []
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

const renaming = ref<NodeItem | null>(null)
const newName = ref('')

function openRename(n: NodeItem) {
  renaming.value = n
  newName.value = n.name
}

async function doRename() {
  if (!renaming.value) return
  try {
    await api.updateNode(renaming.value.id, { name: newName.value.trim() })
    renaming.value = null
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

function remove(n: NodeItem) {
  dialog.warning({
    title: '删除节点',
    content: `确定删除「${n.name}」？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteNode(n.id)
        await load()
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

const columns: DataTableColumns<NodeItem> = [
  { type: 'selection' },
  {
    title: '名称',
    key: 'name',
    minWidth: 200,
    render: (n) => h('span', { class: n.enabled ? '' : 'muted' }, n.name),
  },
  {
    title: '协议',
    key: 'type',
    width: 110,
    render: (n) => h(NTag, { size: 'small', bordered: false }, () => h('span', { class: 'mono' }, n.type)),
  },
  { title: '地址', key: 'server', minWidth: 220, render: (n) => h('span', { class: 'mono muted' }, `${n.server}:${n.port}`) },
  { title: '节点源', key: 'source_id', minWidth: 120, render: (n) => sourceMap.value.get(n.source_id)?.name ?? '—' },
  {
    title: '启用',
    key: 'enabled',
    width: 72,
    render: (n) => h(NSwitch, { size: 'small', value: n.enabled, onUpdateValue: (v: boolean) => toggle(n, v) }),
  },
  {
    title: '',
    key: 'actions',
    width: 150,
    align: 'right',
    render: (n) =>
      isManual(n)
        ? h(NSpace, { size: 'small', justify: 'end', wrap: false }, () => [
            h(NButton, { size: 'small', quaternary: true, onClick: () => openRename(n) }, () => '改名'),
            h(NButton, { size: 'small', quaternary: true, type: 'error', onClick: () => remove(n) }, () => '删除'),
          ])
        : h('span', { class: 'muted', style: 'font-size: 12px' }, '随订阅更新'),
  },
]
</script>

<template>
  <PageHeader title="节点" description="所有节点源里的节点都在这里。停用的节点不会出现在任何配置方案中。" />
  <div class="toolbar">
    <NSelect
      :value="sourceFilter"
      :options="sourceOptions"
      @update:value="(v: unknown) => (sourceFilter = (v as number | null) ?? null)"
      clearable
      placeholder="全部节点源"
      style="width: 180px"
    />
    <NInputGroup style="width: 280px">
      <NInput v-model:value="keyword" placeholder="按名称搜索" clearable @keyup.enter="load" />
      <NButton @click="load">搜索</NButton>
    </NInputGroup>
    <div v-if="checked.length" class="toolbar__bulk">
      <span class="muted">已选 <span class="mono">{{ checked.length }}</span> 个</span>
      <NButton size="small" secondary type="primary" @click="bulk(true)">启用</NButton>
      <NButton size="small" secondary @click="bulk(false)">停用</NButton>
    </div>
  </div>
  <NDataTable
    v-model:checked-row-keys="checked"
    :columns="columns"
    :data="nodes"
    :loading="loading"
    :row-key="(n: NodeItem) => n.id"
    :pagination="{ pageSize: 50 }"
    :scroll-x="900"
  >
    <template #empty>
      <NEmpty :description="keyword || sourceFilter !== null ? '没有符合条件的节点' : '还没有节点。先到「节点源」导入分享链接或添加机场订阅。'" />
    </template>
  </NDataTable>

  <NModal
    :show="renaming !== null"
    preset="card"
    title="节点改名"
    style="width: 420px"
    @update:show="(v: boolean) => { if (!v) renaming = null }"
  >
    <NInput v-model:value="newName" @keyup.enter="doRename" />
    <template #footer>
      <NSpace justify="end">
        <NButton @click="renaming = null">取消</NButton>
        <NButton type="primary" :disabled="!newName.trim()" @click="doRename">保存</NButton>
      </NSpace>
    </template>
  </NModal>
</template>

<style scoped>
.toolbar {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}
.toolbar__bulk {
  align-items: center;
  display: flex;
  gap: 8px;
  margin-left: auto;
}
</style>
