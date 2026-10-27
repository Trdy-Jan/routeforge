<script setup lang="ts">
import { computed, h, onMounted, ref, watch } from 'vue'
import {
  NButton, NDataTable, NInput, NModal, NSelect, NSpace, NSwitch, NTag, useDialog, useMessage,
  type DataTableColumns, type DataTableRowKey,
} from 'naive-ui'
import { api } from '../api'
import type { NodeItem, Source } from '../api/types'

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
    message.success(`已${enabled ? '启用' : '禁用'} ${r.updated} 个节点`)
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
  { title: '名称', key: 'name' },
  { title: '协议', key: 'type', render: (n) => h(NTag, { size: 'small' }, () => n.type) },
  { title: '地址', key: 'server', render: (n) => `${n.server}:${n.port}` },
  { title: '节点源', key: 'source_id', render: (n) => sourceMap.value.get(n.source_id)?.name ?? '—' },
  {
    title: '启用',
    key: 'enabled',
    render: (n) => h(NSwitch, { value: n.enabled, onUpdateValue: (v: boolean) => toggle(n, v) }),
  },
  {
    title: '操作',
    key: 'actions',
    render: (n) =>
      isManual(n)
        ? h(NSpace, { size: 'small' }, () => [
            h(NButton, { size: 'small', onClick: () => openRename(n) }, () => '改名'),
            h(NButton, { size: 'small', type: 'error', ghost: true, onClick: () => remove(n) }, () => '删除'),
          ])
        : '订阅节点（随订阅更新）',
  },
]
</script>

<template>
  <NSpace vertical size="large">
    <h2 style="margin: 0">节点</h2>
    <NSpace>
      <NSelect
        :value="sourceFilter"
        :options="sourceOptions"
        @update:value="(v: unknown) => (sourceFilter = (v as number | null) ?? null)"
        clearable
        placeholder="全部节点源"
        style="width: 200px"
      />
      <NInput v-model:value="keyword" placeholder="按名称搜索" clearable style="width: 220px" @keyup.enter="load" />
      <NButton @click="load">搜索</NButton>
      <NButton :disabled="!checked.length" @click="bulk(true)">启用所选</NButton>
      <NButton :disabled="!checked.length" @click="bulk(false)">禁用所选</NButton>
    </NSpace>
    <NDataTable
      v-model:checked-row-keys="checked"
      :columns="columns"
      :data="nodes"
      :loading="loading"
      :row-key="(n: NodeItem) => n.id"
      :pagination="{ pageSize: 50 }"
    />
  </NSpace>

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
