<script setup lang="ts">
import { computed } from 'vue'
import { NAlert, NButton, NCheckbox, NInput, NSelect, NSpace } from 'naive-ui'
import { RULE_TYPES, type Profile, type Rule, type RuleType } from '../api/types'
import { insertBeforeMatch, moveItem, newRule, targetOptions } from '../lib/profile'

const profile = defineModel<Profile>({ required: true })

const NO_RESOLVE_TYPES: RuleType[] = ['IP-CIDR', 'IP-CIDR6', 'GEOIP', 'RULE-SET']
const PLACEHOLDERS: Partial<Record<RuleType, string>> = {
  DOMAIN: 'www.example.com',
  'DOMAIN-SUFFIX': 'example.com',
  'DOMAIN-KEYWORD': 'google',
  'IP-CIDR': '10.0.0.0/8',
  'IP-CIDR6': '2001:db8::/32',
  GEOSITE: 'cn',
  GEOIP: 'CN',
  'PROCESS-NAME': 'Telegram.exe',
}

const typeOptions = RULE_TYPES.map((t) => ({ label: t, value: t }))
const targets = computed(() => targetOptions(profile.value).map((t) => ({ label: t, value: t })))
const providerOptions = computed(() => profile.value.rule_providers.map((p) => ({ label: p.name, value: p.name })))
const hasMatch = computed(() => profile.value.rules.some((r) => r.type === 'MATCH'))
const defaultTarget = computed(() => profile.value.groups[0]?.name ?? 'DIRECT')

function add() {
  profile.value.rules = insertBeforeMatch(profile.value.rules, newRule(defaultTarget.value))
}

function addMatch() {
  profile.value.rules.push({ type: 'MATCH', value: '', target: defaultTarget.value, no_resolve: false })
}

function setType(r: Rule, t: RuleType) {
  if (r.type !== t) r.value = ''
  r.type = t
  if (!NO_RESOLVE_TYPES.includes(t)) r.no_resolve = false
}

function move(i: number, delta: number) {
  profile.value.rules = moveItem(profile.value.rules, i, delta)
}

function remove(i: number) {
  profile.value.rules.splice(i, 1)
}
</script>

<template>
  <NSpace vertical>
    <NAlert v-if="!hasMatch" type="warning">
      规则需要以一条 MATCH 结尾（决定未匹配任何规则的流量走向）。
      <NButton text type="primary" @click="addMatch">添加 MATCH</NButton>
    </NAlert>
    <NAlert type="info">规则从上到下依次匹配，命中第一条即停止。</NAlert>
    <div v-for="(r, i) in profile.rules" :key="i" class="row">
      <span class="idx">{{ i + 1 }}</span>
      <NSelect
        :value="r.type"
        :options="typeOptions"
        style="width: 170px"
        @update:value="(v: unknown) => setType(r, v as RuleType)"
      />
      <NSelect
        v-if="r.type === 'RULE-SET'"
        :value="r.value || null"
        :options="providerOptions"
        placeholder="选择规则集"
        style="width: 240px"
        @update:value="(v: unknown) => (r.value = String(v ?? ''))"
      />
      <NInput v-else-if="r.type !== 'MATCH'" v-model:value="r.value" :placeholder="PLACEHOLDERS[r.type]" style="width: 240px" />
      <span v-else class="match-text">其余所有流量</span>
      <span>→</span>
      <NSelect
        :value="r.target"
        :options="targets"
        style="width: 170px"
        @update:value="(v: unknown) => (r.target = v as string)"
      />
      <NCheckbox v-if="NO_RESOLVE_TYPES.includes(r.type)" v-model:checked="r.no_resolve">no-resolve</NCheckbox>
      <NButton size="tiny" quaternary @click="move(i, -1)">↑</NButton>
      <NButton size="tiny" quaternary @click="move(i, 1)">↓</NButton>
      <NButton size="tiny" quaternary type="error" @click="remove(i)">✕</NButton>
    </div>
    <NButton dashed block @click="add">添加规则（插在 MATCH 之前）</NButton>
  </NSpace>
</template>

<style scoped>
.row {
  align-items: center;
  display: flex;
  gap: 8px;
}
.idx {
  color: #999;
  text-align: right;
  width: 28px;
}
.match-text {
  color: #999;
  width: 240px;
}
</style>
