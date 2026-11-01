<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { NButton, NForm, NFormItem, NInput, NSelect, NSpace, NSwitch, useMessage } from 'naive-ui'
import { api } from '../api'
import type { ProfileSummary, PushStatus } from '../api/types'
import { formatTime } from '../lib/format'
import PageHeader from '../components/PageHeader.vue'

const message = useMessage()

const form = reactive({
  router_url: '',
  username: 'root',
  password: '',
  config_name: '',
  profile_id: null as number | null,
  auto_push: false,
})
const hasPassword = ref(false)
const status = ref<PushStatus | null>(null)
const profiles = ref<ProfileSummary[]>([])
const saving = ref(false)
const testing = ref(false)
const pushing = ref(false)

const profileOptions = computed(() => profiles.value.map((p) => ({ label: p.name, value: p.id })))

function apply(s: Awaited<ReturnType<typeof api.getOpenClash>>) {
  Object.assign(form, {
    router_url: s.router_url,
    username: s.username,
    password: '',
    config_name: s.config_name,
    profile_id: s.profile_id,
    auto_push: s.auto_push,
  })
  hasPassword.value = s.has_password
  status.value = s.status
}

onMounted(async () => {
  try {
    const [s, ps] = await Promise.all([api.getOpenClash(), api.listProfiles()])
    apply(s)
    profiles.value = ps
  } catch (e) {
    message.error((e as Error).message)
  }
})

async function persist(): Promise<boolean> {
  try {
    apply(await api.saveOpenClash({ ...form, password: form.password || undefined }))
    return true
  } catch (e) {
    message.error((e as Error).message)
    return false
  }
}

async function save() {
  saving.value = true
  if (await persist()) message.success('已保存')
  saving.value = false
}

async function test() {
  testing.value = true
  try {
    if (!(await persist())) return
    const r = await api.testOpenClash()
    if (r.ok) message.success(r.message)
    else message.error(r.message)
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    testing.value = false
  }
}

async function push() {
  pushing.value = true
  try {
    if (!(await persist())) return
    const r = await api.pushOpenClash()
    status.value = r
    if (r.ok) message.success(r.message)
    else message.error(r.message)
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    pushing.value = false
  }
}
</script>

<template>
  <PageHeader
    title="设置"
    description="方案内容变化后，自动登录路由器并让 OpenClash 立即重新拉取订阅，不必等它的定时更新。"
  />

  <section class="surface panel">
    <h2>推送到 OpenClash</h2>
    <NForm label-placement="left" label-width="120" :show-feedback="false" class="form">
      <NFormItem label="路由器地址">
        <NInput v-model:value="form.router_url" class="mono" placeholder="http://192.168.31.2" />
      </NFormItem>
      <NFormItem label="用户名">
        <NInput v-model:value="form.username" placeholder="root" />
      </NFormItem>
      <NFormItem label="密码">
        <NInput
          v-model:value="form.password"
          type="password"
          show-password-on="click"
          :placeholder="hasPassword ? '已保存，留空则不修改' : 'LuCI 登录密码'"
          :input-props="{ autocomplete: 'new-password' }"
        />
      </NFormItem>
      <NFormItem label="配置文件名">
        <NInput v-model:value="form.config_name" class="mono" placeholder="192_168_31_88" />
      </NFormItem>
      <p class="hint muted">OpenClash「配置文件订阅」里的配置文件名，不含 .yaml。</p>
      <NFormItem label="对应方案">
        <NSelect
          v-model:value="form.profile_id"
          :options="profileOptions"
          clearable
          placeholder="该配置文件订阅的是哪个方案"
        />
      </NFormItem>
      <NFormItem label="自动推送">
        <NSwitch v-model:value="form.auto_push" :disabled="form.profile_id === null" />
      </NFormItem>
      <p class="hint muted">开启后，所选方案的订阅内容一有变化（编辑方案、节点或订阅源刷新），几秒内就会通知 OpenClash 更新。</p>
    </NForm>

    <NSpace class="actions">
      <NButton type="primary" :loading="saving" @click="save">保存</NButton>
      <NButton :loading="testing" @click="test">测试登录</NButton>
      <NButton :loading="pushing" @click="push">立即更新 OpenClash</NButton>
    </NSpace>

    <p v-if="status" class="last">
      <span class="status" :class="status.ok ? 'status--ok' : 'status--error'">
        {{ status.trigger === 'auto' ? '自动推送' : '手动推送' }} · {{ formatTime(status.at) }}
      </span>
      <span class="last__msg">{{ status.message }}</span>
    </p>
  </section>
</template>

<style scoped>
.panel {
  max-width: 720px;
  padding: 20px 24px 22px;
}
h2 {
  font-size: 16px;
  font-weight: 650;
  margin: 0 0 16px;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.hint {
  font-size: 13px;
  margin: -8px 0 0 120px;
}
.actions {
  margin-top: 22px;
}
.last {
  display: flex;
  flex-wrap: wrap;
  font-size: 13px;
  gap: 10px;
  margin: 16px 0 0;
}
.last__msg {
  color: var(--rf-muted);
}
@media (max-width: 640px) {
  .panel {
    padding: 16px;
  }
  .hint {
    margin-left: 0;
  }
}
</style>
