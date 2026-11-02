<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NForm, NFormItem, NModal, NRadio, NRadioGroup, NSelect, useMessage } from 'naive-ui'
import { api } from '../api'
import type { LibraryItem, ProfileDetail, ProfileSummary } from '../api/types'
import { copyText } from '../lib/clipboard'
import { targetOptions } from '../lib/profile'
import { addLibraryRule, canUseGeoRule, type AddMode } from '../lib/ruleLibrary'
import PageHeader from '../components/PageHeader.vue'
import RuleLibraryBrowser from '../components/RuleLibraryBrowser.vue'

const message = useMessage()

const showAdd = ref(false)
const addItem = ref<LibraryItem | null>(null)
const profiles = ref<ProfileSummary[]>([])
const profileId = ref<number | null>(null)
const detail = ref<ProfileDetail | null>(null)
const target = ref<string | null>(null)
const mode = ref<AddMode>('rule-set')
const saving = ref(false)

const profileOptions = computed(() => profiles.value.map((p) => ({ label: p.name, value: p.id })))
const targets = computed(() => (detail.value ? targetOptions(detail.value.profile).map((t) => ({ label: t, value: t })) : []))
const geoLabel = computed(() => (addItem.value?.category === 'geoip' ? '用 GEOIP 规则' : '用 GEOSITE 规则'))

async function copy(text: string, what: string) {
  if (await copyText(text)) message.success(`已复制${what}`)
  else message.error('复制失败，请手动选择复制')
}

async function openAdd(item: LibraryItem) {
  addItem.value = item
  mode.value = 'rule-set'
  showAdd.value = true
  try {
    profiles.value = await api.listProfiles()
    if (profileId.value !== null && profiles.value.some((p) => p.id === profileId.value)) {
      await pickProfile(profileId.value)
    } else {
      profileId.value = null
      detail.value = null
      target.value = null
    }
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function pickProfile(id: number) {
  profileId.value = id
  detail.value = null
  try {
    detail.value = await api.getProfile(id)
    const names = targetOptions(detail.value.profile)
    if (!target.value || !names.includes(target.value)) target.value = detail.value.profile.groups[0]?.name ?? 'DIRECT'
  } catch (e) {
    message.error((e as Error).message)
  }
}

async function confirmAdd() {
  if (!addItem.value || profileId.value === null || !target.value) return
  saving.value = true
  try {
    // 确认时重新获取，避免覆盖期间在别处做的修改
    const fresh = await api.getProfile(profileId.value)
    const result = addLibraryRule(fresh.profile, addItem.value, mode.value, target.value)
    if (result.status === 'exists') {
      message.warning(`已存在：第 ${result.index + 1} 条 → ${result.target}`)
      return
    }
    await api.saveProfile(profileId.value, result.profile)
    message.success(`已加入「${fresh.profile.name}」`)
    showAdd.value = false
  } catch (e) {
    message.error((e as Error).message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <PageHeader title="规则库" description="搜索 MetaCubeX/meta-rules-dat 的规则，查看其中的域名或 IP 段，并加入方案。" />
  <section class="surface panel">
    <RuleLibraryBrowser>
      <template #actions="{ item }">
        <NButton size="small" @click="copy(item.name, '名称')">复制名称</NButton>
        <NButton size="small" @click="copy(item.url, ' URL')">复制 URL</NButton>
        <NButton size="small" type="primary" @click="openAdd(item)">加入到方案</NButton>
      </template>
    </RuleLibraryBrowser>
  </section>

  <NModal
    v-model:show="showAdd"
    preset="card"
    :title="`加入到方案：${addItem?.name ?? ''}`"
    style="width: min(480px, calc(100vw - 32px))"
  >
    <NForm label-placement="left" label-width="80" :show-feedback="false" class="add-form">
      <NFormItem label="方案">
        <NSelect
          :value="profileId"
          :options="profileOptions"
          placeholder="选择方案"
          @update:value="(v: unknown) => pickProfile(v as number)"
        />
      </NFormItem>
      <NFormItem label="目标">
        <NSelect
          :value="target"
          :options="targets"
          :disabled="!detail"
          placeholder="选择目标分组"
          @update:value="(v: unknown) => (target = v as string)"
        />
      </NFormItem>
      <NFormItem label="加入方式">
        <NRadioGroup v-model:value="mode">
          <NRadio value="rule-set">规则集 RULE-SET</NRadio>
          <NRadio value="geo" :disabled="!addItem || !canUseGeoRule(addItem)">{{ geoLabel }}</NRadio>
        </NRadioGroup>
      </NFormItem>
    </NForm>
    <template #footer>
      <div class="add-footer">
        <NButton @click="showAdd = false">取消</NButton>
        <NButton type="primary" :loading="saving" :disabled="!detail || !target" @click="confirmAdd">加入</NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.panel {
  padding: 18px 20px 20px;
}
.add-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.add-footer {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}
</style>
