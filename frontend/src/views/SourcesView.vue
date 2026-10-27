<script setup lang="ts">
import { h, onMounted, reactive, ref } from 'vue'
import {
  NAlert, NButton, NDataTable, NEmpty, NForm, NFormItem, NInput, NInputNumber, NModal, NRadioButton, NRadioGroup, NSpace,
  NTag, NTooltip, useDialog, useMessage, type DataTableColumns,
} from 'naive-ui'
import { api } from '../api'
import type { LineError, Source, SourceKind } from '../api/types'
import { formatBytes, formatEpoch, formatTime } from '../lib/format'
import PageHeader from '../components/PageHeader.vue'

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
const importing = ref(false)

function openImport(s: Source) {
  importTarget.value = s
  importText.value = ''
  importErrors.value = []
}

async function doImport() {
  if (!importTarget.value || importing.value) return
  importing.value = true
  try {
    const r = await api.importNodes(importTarget.value.id, importText.value)
    importErrors.value = r.errors
    if (r.added === 0) message.warning('没有导入任何节点')
    else message.success(`已导入 ${r.added} 个节点`)
    if (r.errors.length === 0) importTarget.value = null
    await load()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    importing.value = false
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
  { title: '名称', key: 'name', minWidth: 140, render: (s) => h('strong', { style: 'font-weight: 600' }, s.name) },
  {
    title: '类型',
    key: 'kind',
    width: 100,
    render: (s) =>
      h(NTag, { size: 'small', bordered: false, type: s.kind === 'subscription' ? 'info' : 'default' }, () =>
        s.kind === 'subscription' ? '机场订阅' : '手动'),
  },
  { title: '节点', key: 'node_count', width: 72, align: 'right', render: (s) => h('span', { class: 'mono' }, s.node_count) },
  {
    title: '状态',
    key: 'last_error',
    minWidth: 160,
    render: (s) => {
      if (!s.last_error) return h('span', { class: 'status status--ok' }, '正常')
      return h(NTooltip, { style: 'max-width: 420px' }, {
        trigger: () => h('span', { class: 'status status--error', style: 'cursor: help' }, '拉取失败'),
        default: () => s.last_error,
      })
    },
  },
  {
    title: '上次拉取',
    key: 'last_fetched_at',
    width: 170,
    render: (s) =>
      s.kind === 'subscription' ? h('span', { class: 'mono muted' }, formatTime(s.last_fetched_at)) : h('span', { class: 'muted' }, '—'),
  },
  { title: '流量', key: 'userinfo', minWidth: 150, render: (s) => h('span', { class: 'muted' }, trafficText(s)) },
  {
    title: '',
    key: 'actions',
    width: 236,
    align: 'right',
    render: (s) =>
      h(NSpace, { size: 'small', justify: 'end', wrap: false }, () => [
        s.kind === 'subscription'
          ? h(NButton, { size: 'small', secondary: true, type: 'primary', onClick: () => refresh(s) }, () => '立即刷新')
          : h(NButton, { size: 'small', secondary: true, type: 'primary', onClick: () => openImport(s) }, () => '导入链接'),
        h(NButton, { size: 'small', quaternary: true, onClick: () => openEdit(s) }, () => '编辑'),
        h(NButton, { size: 'small', quaternary: true, type: 'error', onClick: () => remove(s) }, () => '删除'),
      ]),
  },
]
</script>

<template>
  <PageHeader title="节点源" description="机场订阅会按设定的间隔自动刷新；手动节点源用来存放你自己粘贴的分享链接。">
    <NButton type="primary" @click="openCreate">新建节点源</NButton>
  </PageHeader>
  <NDataTable
    :columns="columns"
    :data="sources"
    :loading="loading"
    :row-key="(s: Source) => s.id"
    :scroll-x="980"
  >
    <template #empty>
      <NEmpty description="还没有节点源。添加一个机场订阅，或新建手动节点源后粘贴分享链接。">
        <template #extra><NButton size="small" type="primary" @click="openCreate">新建节点源</NButton></template>
      </NEmpty>
    </template>
  </NDataTable>

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
        <NFormItem label="订阅链接"><NInput v-model:value="form.url" class="mono" placeholder="https://..." /></NFormItem>
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
      class="mono"
      placeholder="每行一个 ss:// vmess:// vless:// trojan:// hysteria2:// tuic:// 链接"
    />
    <NAlert v-if="importErrors.length" type="warning" title="以下行未能导入" style="margin-top: 12px">
      <div v-for="(e, i) in importErrors" :key="i"><code>{{ e.line }}</code>：{{ e.message }}</div>
    </NAlert>
    <template #footer>
      <NSpace justify="end">
        <NButton @click="importTarget = null">关闭</NButton>
        <NButton type="primary" :loading="importing" @click="doImport">导入</NButton>
      </NSpace>
    </template>
  </NModal>
</template>
