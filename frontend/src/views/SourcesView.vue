<script setup lang="ts">
import { h, onMounted, reactive, ref } from 'vue'
import {
  NAlert, NButton, NDataTable, NForm, NFormItem, NInput, NInputNumber, NModal, NRadioButton, NRadioGroup, NSpace,
  NTag, NText, useDialog, useMessage, type DataTableColumns,
} from 'naive-ui'
import { api } from '../api'
import type { LineError, Source, SourceKind } from '../api/types'
import { formatBytes, formatEpoch, formatTime } from '../lib/format'

const message = useMessage()
const dialog = useDialog()

const sources = ref<Source[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    sources.value = await api.listSources()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

// —— 新建 / 编辑 ——
const showForm = ref(false)
const editing = ref<Source | null>(null)
const saving = ref(false)
const form = reactive({ kind: 'manual' as SourceKind, name: '', url: '', refresh_interval: 360, user_agent: 'clash.meta' })

function openCreate() {
  editing.value = null
  Object.assign(form, { kind: 'manual', name: '', url: '', refresh_interval: 360, user_agent: 'clash.meta' })
  showForm.value = true
}

function openEdit(s: Source) {
  editing.value = s
  Object.assign(form, {
    kind: s.kind, name: s.name, url: s.url ?? '', refresh_interval: s.refresh_interval, user_agent: s.user_agent,
  })
  showForm.value = true
}

async function save() {
  saving.value = true
  const subFields =
    form.kind === 'subscription'
      ? { url: form.url, refresh_interval: form.refresh_interval, user_agent: form.user_agent }
      : {}
  try {
    if (editing.value) {
      await api.updateSource(editing.value.id, { name: form.name, ...subFields })
    } else {
      const created = await api.createSource({ kind: form.kind, name: form.name, ...subFields })
      if (created.last_error) message.warning(`已创建，但首次拉取失败：${created.last_error}`)
    }
    showForm.value = false
    await load()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}

// —— 刷新 ——
async function refresh(s: Source) {
  try {
    const r = await api.refreshSource(s.id)
    if (r.ok) message.success(`刷新完成：新增 ${r.added}，更新 ${r.updated}，移除 ${r.removed}`)
    else message.error(r.error ?? '刷新失败')
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

// —— 导入分享链接 ——
const importTarget = ref<Source | null>(null)
const importText = ref('')
const importErrors = ref<LineError[]>([])

function openImport(s: Source) {
  importTarget.value = s
  importText.value = ''
  importErrors.value = []
}

async function doImport() {
  if (!importTarget.value) return
  try {
    const r = await api.importNodes(importTarget.value.id, importText.value)
    importErrors.value = r.errors
    message.success(`已导入 ${r.added} 个节点`)
    if (r.errors.length === 0) importTarget.value = null
    await load()
  } catch (e) {
    message.error((e as Error).message)
  }
}

// —— 删除 ——
function remove(s: Source) {
  dialog.warning({
    title: '删除节点源',
    content: `确定删除「${s.name}」及其 ${s.node_count} 个节点？引用这些节点的方案会在预览中出现警告。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteSource(s.id)
        message.success('已删除')
        await load()
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

function trafficText(s: Source): string {
  const u = s.userinfo
  if (!u) return '—'
  const used = formatBytes((u.upload ?? 0) + (u.download ?? 0))
  const expire = u.expire ? `，${formatEpoch(u.expire)} 到期` : ''
  return `${used} / ${formatBytes(u.total)}${expire}`
}

const columns: DataTableColumns<Source> = [
  { title: '名称', key: 'name' },
  {
    title: '类型',
    key: 'kind',
    render: (s) =>
      h(NTag, { size: 'small', type: s.kind === 'subscription' ? 'info' : 'default' }, () =>
        s.kind === 'subscription' ? '机场订阅' : '手动'),
  },
  { title: '节点数', key: 'node_count' },
  { title: '上次拉取', key: 'last_fetched_at', render: (s) => (s.kind === 'subscription' ? formatTime(s.last_fetched_at) : '—') },
  {
    title: '状态',
    key: 'last_error',
    render: (s) =>
      s.last_error ? h(NText, { type: 'error' }, () => s.last_error) : h(NText, { type: 'success' }, () => '正常'),
  },
  { title: '流量', key: 'userinfo', render: trafficText },
  {
    title: '操作',
    key: 'actions',
    render: (s) =>
      h(NSpace, { size: 'small' }, () => [
        s.kind === 'subscription'
          ? h(NButton, { size: 'small', onClick: () => refresh(s) }, () => '立即刷新')
          : h(NButton, { size: 'small', onClick: () => openImport(s) }, () => '导入链接'),
        h(NButton, { size: 'small', onClick: () => openEdit(s) }, () => '编辑'),
        h(NButton, { size: 'small', type: 'error', ghost: true, onClick: () => remove(s) }, () => '删除'),
      ]),
  },
]
</script>

<template>
  <NSpace vertical size="large">
    <NSpace justify="space-between" align="center">
      <h2 style="margin: 0">节点源</h2>
      <NButton type="primary" @click="openCreate">新建节点源</NButton>
    </NSpace>
    <NDataTable :columns="columns" :data="sources" :loading="loading" :row-key="(s: Source) => s.id" />
  </NSpace>

  <NModal v-model:show="showForm" preset="card" :title="editing ? '编辑节点源' : '新建节点源'" style="width: 520px">
    <NForm label-placement="left" label-width="96">
      <NFormItem v-if="!editing" label="类型">
        <NRadioGroup :value="form.kind" @update:value="(v: unknown) => (form.kind = v as SourceKind)">
          <NRadioButton value="manual">手动</NRadioButton>
          <NRadioButton value="subscription">机场订阅</NRadioButton>
        </NRadioGroup>
      </NFormItem>
      <NFormItem label="名称"><NInput v-model:value="form.name" /></NFormItem>
      <template v-if="form.kind === 'subscription'">
        <NFormItem label="订阅链接"><NInput v-model:value="form.url" placeholder="https://..." /></NFormItem>
        <NFormItem label="刷新间隔">
          <NInputNumber
            :value="form.refresh_interval"
            :min="10"
            :max="10080"
            @update:value="(v: number | null) => (form.refresh_interval = v ?? 360)"
          >
            <template #suffix>分钟</template>
          </NInputNumber>
        </NFormItem>
        <NFormItem label="User-Agent"><NInput v-model:value="form.user_agent" /></NFormItem>
      </template>
    </NForm>
    <template #footer>
      <NSpace justify="end">
        <NButton @click="showForm = false">取消</NButton>
        <NButton type="primary" :loading="saving" @click="save">保存</NButton>
      </NSpace>
    </template>
  </NModal>

  <NModal
    :show="importTarget !== null"
    preset="card"
    title="导入分享链接"
    style="width: 640px"
    @update:show="(v: boolean) => { if (!v) importTarget = null }"
  >
    <NInput
      v-model:value="importText"
      type="textarea"
      :rows="10"
      placeholder="每行一个 ss:// vmess:// vless:// trojan:// hysteria2:// tuic:// 链接"
    />
    <NAlert v-if="importErrors.length" type="warning" title="以下行未能导入" style="margin-top: 12px">
      <div v-for="(e, i) in importErrors" :key="i"><code>{{ e.line }}</code>：{{ e.message }}</div>
    </NAlert>
    <template #footer>
      <NSpace justify="end">
        <NButton @click="importTarget = null">关闭</NButton>
        <NButton type="primary" @click="doImport">导入</NButton>
      </NSpace>
    </template>
  </NModal>
</template>
