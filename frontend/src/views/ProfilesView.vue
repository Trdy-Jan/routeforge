<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton, NDataTable, NInput, NInputGroup, NModal, NSpace, useDialog, useMessage, type DataTableColumns,
} from 'naive-ui'
import { api } from '../api'
import type { ProfileSummary } from '../api/types'
import { copyText } from '../lib/clipboard'
import { subscriptionUrl } from '../lib/profile'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()

const profiles = ref<ProfileSummary[]>([])
const loading = ref(false)
const showCreate = ref(false)
const newName = ref('')

async function load() {
  loading.value = true
  try {
    profiles.value = await api.listProfiles()
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function create() {
  try {
    const p = await api.createProfile(newName.value.trim())
    showCreate.value = false
    newName.value = ''
    router.push({ name: 'profile-edit', params: { id: p.id } })
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function copy(url: string) {
  if (await copyText(url)) message.success('已复制订阅链接')
  else message.warning('无法访问剪贴板，请手动复制')
}

function remove(p: ProfileSummary) {
  dialog.warning({
    title: '删除方案',
    content: `确定删除「${p.name}」？使用该订阅链接的客户端将无法再更新。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.deleteProfile(p.id)
        await load()
      } catch (e) {
        message.error((e as Error).message)
      }
    },
  })
}

const columns: DataTableColumns<ProfileSummary> = [
  { title: '名称', key: 'name' },
  {
    title: '订阅链接',
    key: 'token',
    render: (p) => {
      const url = subscriptionUrl(window.location.origin, p.token)
      return h(NInputGroup, null, () => [
        h(NInput, { value: url, readonly: true, size: 'small' }),
        h(NButton, { size: 'small', onClick: () => copy(url) }, () => '复制'),
      ])
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 160,
    render: (p) =>
      h(NSpace, { size: 'small' }, () => [
        h(NButton, { size: 'small', type: 'primary', onClick: () => router.push({ name: 'profile-edit', params: { id: p.id } }) },
          () => '编辑'),
        h(NButton, { size: 'small', type: 'error', ghost: true, onClick: () => remove(p) }, () => '删除'),
      ]),
  },
]
</script>

<template>
  <NSpace vertical size="large">
    <NSpace justify="space-between" align="center">
      <h2 style="margin: 0">配置方案</h2>
      <NButton type="primary" @click="showCreate = true">新建方案</NButton>
    </NSpace>
    <NDataTable :columns="columns" :data="profiles" :loading="loading" :row-key="(p: ProfileSummary) => p.id" />
  </NSpace>

  <NModal v-model:show="showCreate" preset="card" title="新建方案" style="width: 420px">
    <NInput v-model:value="newName" placeholder="方案名称，例如 家里电脑" @keyup.enter="create" />
    <template #footer>
      <NSpace justify="end">
        <NButton @click="showCreate = false">取消</NButton>
        <NButton type="primary" :disabled="!newName.trim()" @click="create">创建</NButton>
      </NSpace>
    </template>
  </NModal>
</template>
