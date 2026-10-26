<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { NButton, NDropdown, NInput, NSpace, NSpin, NTabPane, NTabs, useMessage } from 'naive-ui'
import { api } from '../api'
import type { Profile, ProfileDetail, TemplateInfo } from '../api/types'
import PreviewPanel from '../components/PreviewPanel.vue'

const props = defineProps<{ id: number }>()
const router = useRouter()
const message = useMessage()

const detail = ref<ProfileDetail | null>(null)
const profile = ref<Profile | null>(null)
const savedJson = ref('')
const version = ref(0)
const templates = ref<TemplateInfo[]>([])
const saving = ref(false)

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
  try {
    const [d, t] = await Promise.all([api.getProfile(props.id), api.listTemplates()])
    templates.value = t
    setDetail(d)
  } catch (e) {
    message.error((e as Error).message)
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
  <NSpin :show="!profile">
    <NSpace v-if="profile && detail" vertical size="large">
      <NSpace align="center" justify="space-between">
        <NSpace align="center">
          <NButton text @click="router.push({ name: 'profiles' })">← 返回</NButton>
          <NInput v-model:value="profile.name" placeholder="方案名称" style="width: 240px" />
        </NSpace>
        <NSpace>
          <NDropdown :options="templateOptions" trigger="click" @select="applyTemplate">
            <NButton>套用模板</NButton>
          </NDropdown>
          <NButton type="primary" :disabled="!dirty || !profile.name.trim()" :loading="saving" @click="save">
            保存
          </NButton>
        </NSpace>
      </NSpace>

      <NTabs type="line" default-value="preview" animated>
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
