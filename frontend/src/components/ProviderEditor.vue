<script setup lang="ts">
import { ref } from 'vue'
import { NAlert, NButton, NEmpty, NInput, NInputNumber, NSelect, NSpace, useDialog, useMessage } from 'naive-ui'
import type { Profile, RuleProvider } from '../api/types'

const profile = defineModel<Profile>({ required: true })
const message = useMessage()
const dialog = useDialog()

const BEHAVIORS = [
  { label: '域名 domain', value: 'domain' },
  { label: 'IP 段 ipcidr', value: 'ipcidr' },
  { label: '混合 classical', value: 'classical' },
]
const FORMATS = [
  { label: 'mrs', value: 'mrs' },
  { label: 'yaml', value: 'yaml' },
  { label: 'text', value: 'text' },
]

const drafts = ref<Record<number, string>>({})

function usage(name: string): number {
  return profile.value.rules.filter((r) => r.type === 'RULE-SET' && r.value === name).length
}

function add() {
  let i = profile.value.rule_providers.length + 1
  while (profile.value.rule_providers.some((p) => p.name === `ruleset-${i}`)) i++
  profile.value.rule_providers.push({ name: `ruleset-${i}`, behavior: 'domain', format: 'mrs', url: '', interval: 86400 })
}

function commitRename(index: number) {
  const draft = drafts.value[index]
  delete drafts.value[index]
  if (draft === undefined) return
  const old = profile.value.rule_providers[index].name
  const name = draft.trim()
  if (name === old) return
  if (!name || profile.value.rule_providers.some((p) => p.name === name)) {
    message.error(`规则集名称「${name}」为空或已存在`)
    return
  }
  profile.value.rule_providers[index].name = name
  for (const r of profile.value.rules) {
    if (r.type === 'RULE-SET' && r.value === old) r.value = name
  }
}

function remove(index: number) {
  const p = profile.value.rule_providers[index]
  const used = usage(p.name)
  dialog.warning({
    title: '删除规则集',
    content: used ? `「${p.name}」被 ${used} 条规则引用，删除后预览会报错。确定删除？` : `确定删除「${p.name}」？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: () => {
      profile.value.rule_providers.splice(index, 1)
    },
  })
}
</script>

<template>
  <NSpace vertical>
    <NAlert type="info">规则集是远程维护的规则列表，在「规则」中用 RULE-SET 类型引用。mrs 格式只支持 domain 和 ipcidr。</NAlert>
    <NEmpty v-if="!profile.rule_providers.length" description="还没有规则集" />
    <div v-for="(p, i) in profile.rule_providers" :key="i" class="row">
      <NInput
        :value="drafts[i] ?? p.name"
        style="width: 180px"
        @update:value="(v: string) => (drafts[i] = v)"
        @blur="commitRename(i)"
        @keyup.enter="commitRename(i)"
      />
      <NSelect
        :value="p.behavior"
        :options="BEHAVIORS"
        style="width: 150px"
        @update:value="(v: unknown) => (p.behavior = v as RuleProvider['behavior'])"
      />
      <NSelect
        :value="p.format"
        :options="FORMATS"
        style="width: 90px"
        @update:value="(v: unknown) => (p.format = v as RuleProvider['format'])"
      />
      <NInput v-model:value="p.url" placeholder="https://..." style="flex: 1" />
      <NInputNumber
        :value="p.interval"
        :min="60"
        style="width: 130px"
        @update:value="(v: number | null) => (p.interval = v ?? 86400)"
      >
        <template #suffix>秒</template>
      </NInputNumber>
      <span class="usage">{{ usage(p.name) }} 条规则</span>
      <NButton size="tiny" quaternary type="error" @click="remove(i)">✕</NButton>
    </div>
    <NButton dashed block @click="add">添加规则集</NButton>
  </NSpace>
</template>

<style scoped>
.row {
  align-items: center;
  display: flex;
  gap: 8px;
}
.usage {
  color: #999;
  width: 70px;
}
</style>
