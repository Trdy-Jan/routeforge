<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import {
  NButton, NDataTable, NEmpty, NInput, NInputGroup, NModal, NSelect, NSpace, NSwitch, NTag, useDialog, useMessage,
  type DataTableColumns, type DataTableRowKey,
} from 'naive-ui'
import { api } from '../api'
import type { NodeItem, Source } from '../api/types'
import PageHeader from '../components/PageHeader.vue'
import { addressText } from '../lib/nodeImport'

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

function bulkRemove() {
  const ids = checked.value.map(Number)
  const selected = nodes.value.filter((n) => ids.includes(n.id))
  const manualCount = selected.filter(isManual).length
  if (manualCount === 0) {
    message.warning('选中的都是订阅节点，会随订阅刷新恢复，不能删除（可以改为停用）')
    return
  }
  const skipped = ids.length - manualCount
  dialog.warning({
    title: '批量删除节点',
    content: `确定删除选中的 ${manualCount} 个节点？` + (skipped ? `其中 ${skipped} 个订阅节点将被跳过。` : ''),
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const r = await api.bulkDeleteNodes(ids)
        message.success(`已删除 ${r.deleted} 个节点` + (r.skipped ? `，跳过 ${r.skipped} 个订阅节点` : ''))
        checked.value = []
        await load()
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

const editing = ref<NodeItem | null>(null)
const editConfig = ref('')
const saving = ref(false)

async function openEdit(n: NodeItem) {
  try {
    editConfig.value = (await api.getNodeConfig(n.id)).config
    editing.value = n
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function doEdit() {
  if (!editing.value) return
  saving.value = true
  try {
    await api.updateNode(editing.value.id, { config: editConfig.value })
    editing.value = null
    message.success('节点已保存')
    await load()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
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
  { title: '地址', key: 'server', minWidth: 220, render: (n) => h('span', { class: 'mono muted' }, addressText(n.server, n.port, n.port_range)) },
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
            h(NButton, { size: 'small', quaternary: true, onClick: () => openEdit(n) }, () => '编辑'),
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
      <NButton size="small" secondary type="error" @click="bulkRemove">删除</NButton>
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
    :show="editing !== null"
    preset="card"
    title="编辑节点"
    style="width: 560px; max-width: calc(100vw - 32px)"
    @update:show="(v: boolean) => { if (!v) editing = null }"
  >
    <p class="muted" style="margin: 0 0 10px; font-size: 13px">
      使用 Clash / Mihomo 的 proxy 格式，可修改名称、协议、地址、端口、认证、TLS 与传输层等全部字段。
    </p>
    <NInput
      v-model:value="editConfig"
      type="textarea"
      class="config-editor"
      :autosize="{ minRows: 10, maxRows: 24 }"
      spellcheck="false"
    />
    <template #footer>
      <NSpace justify="end">
        <NButton @click="editing = null">取消</NButton>
        <NButton type="primary" :loading="saving" :disabled="!editConfig.trim()" @click="doEdit">保存</NButton>
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
.config-editor :deep(textarea) {
  font-family: var(--rf-mono);
  font-size: 13px;
}
</style>
