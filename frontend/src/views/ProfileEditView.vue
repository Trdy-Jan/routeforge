<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { NAlert, NButton, NDropdown, NInput, NResult, NSpace, NSpin, NTabPane, NTabs, useMessage } from 'naive-ui'
import { api } from '../api'
import type { IssueSection, NodeItem, Preview, Profile, ProfileDetail, Source, TemplateInfo } from '../api/types'
import ChainEditor from '../components/ChainEditor.vue'
import GroupEditor from '../components/GroupEditor.vue'
import IssueList from '../components/IssueList.vue'
import PreviewPanel from '../components/PreviewPanel.vue'
import ProviderEditor from '../components/ProviderEditor.vue'
import RuleEditor from '../components/RuleEditor.vue'

const props = defineProps<{ id: number }>()
const router = useRouter()
const message = useMessage()

const detail = ref<ProfileDetail | null>(null)
const profile = ref<Profile | null>(null)
const savedJson = ref('')
const templates = ref<TemplateInfo[]>([])
const nodes = ref<NodeItem[]>([])
const sources = ref<Source[]>([])
const saving = ref(false)
const loadError = ref<string | null>(null)
const tab = ref<IssueSection | 'preview'>('groups')
const preview = ref<Preview | null>(null)
const previewLoading = ref(false)

const dirty = computed(() => profile.value !== null && JSON.stringify(profile.value) !== savedJson.value)
const templateOptions = computed(() =>
  templates.value.map((t) => ({ label: t.name, key: t.id, props: { title: t.description } })),
)

const issues = computed(() => preview.value?.issues ?? [])

function issueCount(section: IssueSection): number {
  return issues.value.filter((i) => i.section === section).length
}

// 标签页标题：有错误时在后面显示红色计数
function tabLabel(label: string, section: IssueSection) {
  return () => {
    const n = issueCount(section)
    return h('span', [label, n ? h('span', { class: 'tab-err', title: `${n} 处错误` }, n) : null])
  }
}

function setDetail(d: ProfileDetail) {
  detail.value = d
  profile.value = structuredClone(d.profile)
  savedJson.value = JSON.stringify(d.profile)
}

let previewSeq = 0
async function loadPreview(): Promise<Preview | null> {
  if (!detail.value) return null
  const mine = ++previewSeq
  previewLoading.value = true
  try {
    const r = await api.preview(detail.value.id)
    if (mine === previewSeq) preview.value = r
    return r
  } catch (e) {
    if (mine === previewSeq) message.error((e as Error).message)
    return null
  } finally {
    if (mine === previewSeq) previewLoading.value = false
  }
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
    loadPreview()
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
    const p = await loadPreview()
    if (p?.issues.length) {
      message.warning(`已保存，但方案有 ${p.issues.length} 处错误，订阅链接不会更新。请按页面上方的提示修改。`, {
        duration: 8000,
      })
    } else {
      message.success('已保存')
    }
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
    loadPreview()
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

      <NAlert
        v-if="issues.length && tab !== 'preview'"
        type="error"
        class="issues-banner"
        :title="`已保存的方案有 ${issues.length} 处错误，订阅链接会继续返回上次成功的版本`"
      >
        <IssueList :issues="issues" @goto="tab = $event" />
      </NAlert>

      <div class="surface editor">
        <NTabs v-model:value="tab" type="line" animated size="large" :tabs-padding="20">
          <NTabPane name="groups" :tab="tabLabel('分组', 'groups')">
            <GroupEditor v-model="profile" :nodes="nodes" :sources="sources" />
          </NTabPane>
          <NTabPane name="rules" :tab="tabLabel(`规则 ${profile.rules.length || ''}`, 'rules')">
            <RuleEditor v-model="profile" />
          </NTabPane>
          <NTabPane name="providers" :tab="tabLabel('规则集', 'providers')">
            <ProviderEditor v-model="profile" />
          </NTabPane>
          <NTabPane name="chains" :tab="tabLabel('链式代理', 'chains')">
            <ChainEditor v-model="profile" :nodes="nodes" />
          </NTabPane>
          <NTabPane name="preview" tab="预览与订阅">
            <PreviewPanel
              :profile-id="detail.id"
              :token="detail.token"
              :dirty="dirty"
              :preview="preview"
              :loading="previewLoading"
              @reload="loadPreview"
              @goto="tab = $event"
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
.issues-banner {
  margin-bottom: 16px;
}
.editor :deep(.tab-err) {
  background: var(--rf-error);
  border-radius: 9px;
  color: #fff;
  display: inline-block;
  font-size: 12px;
  line-height: 18px;
  margin-left: 6px;
  min-width: 18px;
  padding: 0 5px;
  text-align: center;
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
