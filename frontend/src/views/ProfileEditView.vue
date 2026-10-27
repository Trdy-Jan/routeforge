<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { NButton, NDropdown, NInput, NResult, NSpace, NSpin, NTabPane, NTabs, useMessage } from 'naive-ui'
import { api } from '../api'
import type { NodeItem, Profile, ProfileDetail, Source, TemplateInfo } from '../api/types'
import ChainEditor from '../components/ChainEditor.vue'
import GroupEditor from '../components/GroupEditor.vue'
import PreviewPanel from '../components/PreviewPanel.vue'
import ProviderEditor from '../components/ProviderEditor.vue'
import RuleEditor from '../components/RuleEditor.vue'

const props = defineProps<{ id: number }>()
const router = useRouter()
const message = useMessage()

const detail = ref<ProfileDetail | null>(null)
const profile = ref<Profile | null>(null)
const savedJson = ref('')
const version = ref(0)
const templates = ref<TemplateInfo[]>([])
const nodes = ref<NodeItem[]>([])
const sources = ref<Source[]>([])
const saving = ref(false)
const loadError = ref<string | null>(null)

const dirty = computed(() => profile.value !== null && JSON.stringify(profile.value) !== savedJson.value)
const templateOptions = computed(() =>
  templates.value.map((t) => ({ label: t.name, key: t.id, props: { title: t.description } })),
)

function setDetail(d: ProfileDetail) {
  detail.value = d
  profile.value = structuredClone(d.profile)
  savedJson.value = JSON.stringify(d.profile)
  version.value++
}

async function load() {
  loadError.value = null
  try {
    const [d, t, n, s] = await Promise.all([
      api.getProfile(props.id), api.listTemplates(), api.listNodes(), api.listSources(),
    ])
    templates.value = t
    nodes.value = n
    sources.value = s
    setDetail(d)
  } catch (e) {
    loadError.value = (e as Error).message
  }
}
onMounted(load)

async function save(): Promise<boolean> {
  if (!profile.value) return false
  saving.value = true
  try {
    setDetail(await api.saveProfile(props.id, profile.value))
    message.success('已保存')
    return true
  } catch (e) {
    message.error((e as Error).message)
    return false
  } finally {
    saving.value = false
  }
}

async function applyTemplate(key: string | number) {
  if (saving.value) return
  if (dirty.value && !(await save())) return
  try {
    const r = await api.applyTemplate(props.id, String(key))
    setDetail(r.profile)
    r.notes.forEach((n) => message.info(n))
    message.success('模板已套用')
  } catch (e) {
    message.error((e as Error).message)
  }
}

function onRotated(d: ProfileDetail) {
  if (detail.value) detail.value = { ...detail.value, token: d.token }
}

onBeforeRouteLeave(() => !dirty.value || window.confirm('有未保存的修改，确定离开？'))

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (dirty.value) e.preventDefault()
}
onMounted(() => window.addEventListener('beforeunload', onBeforeUnload))
onUnmounted(() => window.removeEventListener('beforeunload', onBeforeUnload))
</script>

<template>
  <NResult v-if="loadError" status="error" title="加载失败" :description="loadError">
    <template #footer>
      <NSpace justify="center">
        <NButton type="primary" @click="load">重试</NButton>
        <NButton @click="router.push({ name: 'profiles' })">返回列表</NButton>
      </NSpace>
    </template>
  </NResult>
  <NSpin v-else :show="!profile">
    <NSpace v-if="profile && detail" vertical size="large">
      <NSpace align="center" justify="space-between">
        <NSpace align="center">
          <NButton text @click="router.push({ name: 'profiles' })">← 返回</NButton>
          <NInput v-model:value="profile.name" :disabled="saving" placeholder="方案名称" style="width: 240px" />
        </NSpace>
        <NSpace>
          <NDropdown :options="templateOptions" :disabled="saving" trigger="click" @select="applyTemplate">
            <NButton :disabled="saving">套用模板</NButton>
          </NDropdown>
          <NButton type="primary" :disabled="saving || !dirty || !profile.name.trim()" :loading="saving" @click="save">
            保存
          </NButton>
        </NSpace>
      </NSpace>

      <NTabs type="line" default-value="groups" animated>
        <NTabPane name="groups" tab="分组">
          <GroupEditor v-model="profile" :nodes="nodes" :sources="sources" />
        </NTabPane>
        <NTabPane name="rules" tab="规则">
          <RuleEditor v-model="profile" />
        </NTabPane>
        <NTabPane name="providers" tab="规则集">
          <ProviderEditor v-model="profile" />
        </NTabPane>
        <NTabPane name="chains" tab="链式代理">
          <ChainEditor v-model="profile" :nodes="nodes" />
        </NTabPane>
        <NTabPane name="preview" tab="预览与订阅">
          <PreviewPanel
            :profile-id="detail.id"
            :token="detail.token"
            :dirty="dirty"
            :version="version"
            @rotated="onRotated"
          />
        </NTabPane>
      </NTabs>
    </NSpace>
  </NSpin>
</template>
