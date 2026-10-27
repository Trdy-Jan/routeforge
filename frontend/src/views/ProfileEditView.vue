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
    <div v-if="profile && detail">
      <div class="editbar">
        <NButton quaternary size="small" class="editbar__back" @click="router.push({ name: 'profiles' })">‹ 配置方案</NButton>
        <NInput
          v-model:value="profile.name"
          :disabled="saving"
          placeholder="方案名称"
          class="editbar__name"
          aria-label="方案名称"
        />
        <span v-if="dirty" class="status status--unsaved">未保存</span>
        <div class="editbar__actions">
          <NDropdown :options="templateOptions" :disabled="saving" trigger="click" @select="applyTemplate">
            <NButton :disabled="saving">套用模板</NButton>
          </NDropdown>
          <NButton type="primary" :disabled="saving || !dirty || !profile.name.trim()" :loading="saving" @click="save">
            保存
          </NButton>
        </div>
      </div>

      <div class="surface editor">
        <NTabs type="line" default-value="groups" animated size="large" :tabs-padding="20">
          <NTabPane name="groups" tab="分组">
            <GroupEditor v-model="profile" :nodes="nodes" :sources="sources" />
          </NTabPane>
          <NTabPane name="rules" :tab="`规则 ${profile.rules.length || ''}`">
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
      </div>
    </div>
  </NSpin>
</template>

<style scoped>
.editbar {
  align-items: center;
  background: var(--rf-canvas);
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin: -32px -4px 0;
  padding: 24px 4px 16px;
  position: sticky;
  top: 0;
  z-index: 10;
}
.editbar__back {
  color: var(--rf-muted);
}
.editbar__name {
  font-size: 18px;
  font-weight: 600;
  max-width: 320px;
}
.editbar__actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}
.status--unsaved {
  color: var(--rf-warning);
  font-size: 13px;
}
.editor {
  padding: 4px 0 20px;
}
.editor :deep(.n-tab-pane) {
  padding: 20px 20px 0;
}
@media (max-width: 860px) {
  .editbar {
    margin-top: -20px;
    padding-top: 16px;
  }
}
</style>
