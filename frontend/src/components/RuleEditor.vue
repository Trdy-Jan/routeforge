<script setup lang="ts">
import { computed, ref } from 'vue'
import { NAlert, NButton, NCheckbox, NDrawer, NDrawerContent, NInput, NSelect, NSpace, useMessage } from 'naive-ui'
import { MULTI_VALUE_RULE_TYPES, RULE_TYPES, type LibraryItem, type Profile, type Rule, type RuleType } from '../api/types'
import { useDragSort } from '../lib/dragSort'
import { insertBeforeMatch, moveRule, newRule, splitRuleValues, targetOptions } from '../lib/profile'
import { addLibraryRule, canUseGeoRule, type AddMode } from '../lib/ruleLibrary'
import RuleLibraryBrowser from './RuleLibraryBrowser.vue'

const profile = defineModel<Profile>({ required: true })
const drag = useDragSort()

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

const message = useMessage()
const showLibrary = ref(false)
const libraryTarget = ref<string | null>(null)
const libraryTargetValue = computed(() =>
  libraryTarget.value && targetOptions(profile.value).includes(libraryTarget.value) ? libraryTarget.value : defaultTarget.value,
)

function addFromLibrary(item: LibraryItem, mode: AddMode) {
  const result = addLibraryRule(profile.value, item, mode, libraryTargetValue.value)
  if (result.status === 'exists') {
    message.warning(`已存在：第 ${result.index + 1} 条 → ${result.target}`)
    return
  }
  profile.value = result.profile
  message.success(`已加入：${item.name} → ${result.target}`)
}

function add() {
  profile.value.rules = insertBeforeMatch(profile.value.rules, newRule(defaultTarget.value))
}

function addMatch() {
  profile.value.rules.push({ type: 'MATCH', value: '', values: [], target: defaultTarget.value, no_resolve: false })
}

function isMulti(t: RuleType) {
  return MULTI_VALUE_RULE_TYPES.includes(t)
}

function setType(r: Rule, t: RuleType) {
  if (r.type !== t) {
    // 多值类型之间切换保留已填的值；切到/离开单值类型时清空
    if (!(isMulti(r.type) && isMulti(t))) r.values = []
    r.value = ''
  }
  r.type = t
  if (!NO_RESOLVE_TYPES.includes(t)) r.no_resolve = false
}

function move(i: number, delta: number) {
  profile.value.rules = moveRule(profile.value.rules, i, i + delta)
}

function drop(from: number, to: number) {
  profile.value.rules = moveRule(profile.value.rules, from, to)
}

function isLastMovable(i: number) {
  const next = profile.value.rules[i + 1]
  return !next || next.type === 'MATCH'
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
    <p class="hint">规则从上到下依次匹配，命中第一条即停止。</p>
    <div
      v-for="(r, i) in profile.rules"
      :key="i"
      class="edit-row"
      :class="{ 'edit-row--match': r.type === 'MATCH' }"
      v-bind="r.type === 'MATCH' ? {} : drag.row('rules', i, drop)"
    >
      <span v-if="r.type === 'MATCH'" class="drag-handle drag-handle--locked" title="MATCH 固定在最后">⠿</span>
      <span v-else v-bind="drag.handle('rules', i)">⠿</span>
      <span class="idx mono">{{ i + 1 }}</span>
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
        class="value-field"
        @update:value="(v: unknown) => (r.value = String(v ?? ''))"
      />
      <NSelect
        v-else-if="isMulti(r.type)"
        :value="r.values"
        multiple
        filterable
        tag
        :show="false"
        :show-arrow="false"
        class="mono value-field values-input"
        :placeholder="`${PLACEHOLDERS[r.type] ?? ''}（回车添加，可粘贴多个）`"
        @update:value="(v: unknown) => (r.values = splitRuleValues(v as string[]))"
      />
      <NInput v-else-if="r.type !== 'MATCH'" v-model:value="r.value" class="mono value-field" :placeholder="PLACEHOLDERS[r.type]" />
      <span v-else class="match-text value-field">其余所有流量</span>
      <span class="arrow" aria-hidden="true">→</span>
      <NSelect
        :value="r.target"
        :options="targets"
        style="width: 170px"
        @update:value="(v: unknown) => (r.target = v as string)"
      />
      <span class="slot-opt">
        <NCheckbox v-if="NO_RESOLVE_TYPES.includes(r.type)" v-model:checked="r.no_resolve">no-resolve</NCheckbox>
      </span>
      <span class="slot-move">
        <template v-if="r.type !== 'MATCH'">
          <NButton size="tiny" quaternary :disabled="i === 0" @click="move(i, -1)">↑</NButton>
          <NButton size="tiny" quaternary :disabled="isLastMovable(i)" @click="move(i, 1)">↓</NButton>
        </template>
      </span>
      <NButton size="tiny" quaternary type="error" @click="remove(i)">✕</NButton>
    </div>
    <div class="add-row">
      <NButton dashed class="add-row__main" @click="add">添加规则（插在 MATCH 之前）</NButton>
      <NButton dashed @click="showLibrary = true">从规则库添加</NButton>
    </div>
  </NSpace>

  <NDrawer v-model:show="showLibrary" placement="right" :width="760" style="max-width: 100vw">
    <NDrawerContent title="从规则库添加" closable>
      <RuleLibraryBrowser>
        <template #actions="{ item }">
          <span class="lib-label">目标</span>
          <NSelect
            :value="libraryTargetValue"
            :options="targets"
            size="small"
            style="width: 160px"
            @update:value="(v: unknown) => (libraryTarget = v as string)"
          />
          <NButton size="small" type="primary" @click="addFromLibrary(item, 'rule-set')">加入为 RULE-SET</NButton>
          <NButton
            size="small"
            :disabled="!canUseGeoRule(item)"
            :title="canUseGeoRule(item) ? '' : '精简规则只能以规则集方式加入'"
            @click="addFromLibrary(item, 'geo')"
          >
            {{ item.category === 'geoip' ? '用 GEOIP 规则' : '用 GEOSITE 规则' }}
          </NButton>
        </template>
      </RuleLibraryBrowser>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.add-row {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
.add-row__main {
  flex: 1;
}
.lib-label {
  color: var(--rf-muted);
  font-size: 13px;
}
.hint {
  color: var(--rf-muted);
  font-size: 13px;
  margin: 0 0 4px;
}
.idx {
  color: var(--rf-faint);
  text-align: right;
  width: 28px;
}
.arrow {
  color: var(--rf-faint);
}
.match-text {
  color: var(--rf-muted);
}
/* 值输入框占满行内剩余宽度；标签多时自动换行增高 */
.value-field {
  flex: 1 1 240px;
  min-width: 240px;
}
/* 右侧固定占位，保证各行的目标分组上下对齐 */
.slot-opt {
  width: 100px;
}
.slot-move {
  display: inline-flex;
  width: 56px;
}
.edit-row--match {
  background: var(--rf-tint);
  border-radius: 6px;
}
</style>
