<script setup lang="ts">
import { h, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import {
  NButton, NDataTable, NEmpty, NInput, NModal, NSpace, NSpin, useDialog, useMessage, type DataTableColumns,
} from 'naive-ui'
import { api } from '../api'
import type { ProfileSummary } from '../api/types'
import PageHeader from '../components/PageHeader.vue'
import SubscriptionLink from '../components/SubscriptionLink.vue'
import { isMobile } from '../lib/viewport'

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
  {
    title: '名称',
    key: 'name',
    minWidth: 160,
    render: (p) =>
      h('a', {
        href: router.resolve({ name: 'profile-edit', params: { id: p.id } }).href,
        class: 'profile-link',
        onClick: (e: MouseEvent) => {
          e.preventDefault()
          router.push({ name: 'profile-edit', params: { id: p.id } })
        },
      }, p.name),
  },
  {
    title: '订阅链接',
    key: 'token',
    minWidth: 360,
    render: (p) => h(SubscriptionLink, { token: p.token, size: 'small' }),
  },
  {
    title: '',
    key: 'actions',
    width: 150,
    align: 'right',
    render: (p) =>
      h(NSpace, { size: 'small', justify: 'end', wrap: false }, () => [
        h(NButton, { size: 'small', quaternary: true, onClick: () => router.push({ name: 'profile-edit', params: { id: p.id } }) },
          () => '编辑'),
        h(NButton, { size: 'small', quaternary: true, type: 'error', onClick: () => remove(p) }, () => '删除'),
      ]),
  },
]
</script>

<template>
  <PageHeader title="配置方案" description="每个方案生成一条订阅链接，在 Clash Verge Rev 等 Mihomo 内核客户端中添加即可。">
    <NButton type="primary" @click="showCreate = true">新建方案</NButton>
  </PageHeader>
  <NDataTable v-if="!isMobile" :columns="columns" :data="profiles" :loading="loading" :row-key="(p: ProfileSummary) => p.id" :scroll-x="720">
    <template #empty>
      <NEmpty description="还没有配置方案。新建一个，再套用模板就能快速得到可用的订阅。">
        <template #extra><NButton size="small" type="primary" @click="showCreate = true">新建方案</NButton></template>
      </NEmpty>
    </template>
  </NDataTable>

  <!-- 手机：每个方案一张卡片，订阅链接独占一行 -->
  <NSpin v-else :show="loading">
    <div v-if="profiles.length" class="m-list">
      <article v-for="p in profiles" :key="p.id" class="m-card">
        <div class="m-card__head">
          <RouterLink :to="{ name: 'profile-edit', params: { id: p.id } }" class="m-card__title profile-link">
            {{ p.name }}
          </RouterLink>
        </div>
        <div style="margin-top: 10px"><SubscriptionLink :token="p.token" size="small" /></div>
        <div class="m-card__actions">
          <NButton size="small" quaternary @click="router.push({ name: 'profile-edit', params: { id: p.id } })">编辑</NButton>
          <NButton size="small" quaternary type="error" @click="remove(p)">删除</NButton>
        </div>
      </article>
    </div>
    <NEmpty v-else-if="!loading" class="m-empty" description="还没有配置方案。新建一个，再套用模板就能快速得到可用的订阅。">
      <template #extra><NButton size="small" type="primary" @click="showCreate = true">新建方案</NButton></template>
    </NEmpty>
  </NSpin>

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

<style scoped>
.profile-link,
:deep(.profile-link) {
  color: var(--rf-text);
  font-weight: 600;
  text-decoration: none;
}
.profile-link:hover,
:deep(.profile-link:hover) {
  color: var(--rf-primary);
  text-decoration: underline;
  text-underline-offset: 3px;
}
</style>
