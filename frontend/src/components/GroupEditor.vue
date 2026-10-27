<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  NButton, NCard, NEmpty, NInput, NInputNumber, NModal, NSelect, NSpace, NTag, NText, useDialog, useMessage,
} from 'naive-ui'
import type { FilterMember, GroupType, Member, NodeItem, Profile, Source } from '../api/types'
import { BUILTIN_TARGETS, memberLabel, moveItem, newGroup, renameGroup, sameMember } from '../lib/profile'
import FilterForm from './FilterForm.vue'

const profile = defineModel<Profile>({ required: true })
const props = defineProps<{ nodes: NodeItem[]; sources: Source[] }>()
const message = useMessage()
const dialog = useDialog()

const GROUP_TYPES = [
  { label: '手动选择', value: 'select' },
  { label: '自动测速', value: 'url-test' },
  { label: '故障转移', value: 'fallback' },
  { label: '负载均衡', value: 'load-balance' },
]

const nodeMap = computed(() => new Map(props.nodes.map((n) => [n.id, n])))
const sourceMap = computed(() => new Map(props.sources.map((s) => [s.id, s])))
const nodeOptions = computed(() =>
  props.nodes.map((n) => ({ label: `${n.name}（${sourceMap.value.get(n.source_id)?.name ?? '?'}）`, value: n.id })),
)

const drafts = ref<Record<number, string>>({})
const filterFor = ref<number | null>(null)

function groupOptions(self: string) {
  return profile.value.groups.filter((g) => g.name !== self).map((g) => ({ label: g.name, value: g.name }))
}

function tagType(m: Member) {
  return ({ node: 'default', group: 'info', builtin: 'warning', filter: 'success' } as const)[m.kind]
}

function commitRename(index: number) {
  const draft = drafts.value[index]
  delete drafts.value[index]
  if (draft === undefined) return
  const old = profile.value.groups[index].name
  const name = draft.trim()
  if (name === old) return
  if (!name) {
    message.error('分组名不能为空')
    return
  }
  if ((BUILTIN_TARGETS as readonly string[]).includes(name) || profile.value.groups.some((g) => g.name === name)) {
    message.error(`分组名「${name}」已存在或是保留名`)
    return
  }
  profile.value = renameGroup(profile.value, old, name)
}

function addGroup() {
  let i = profile.value.groups.length + 1
  while (profile.value.groups.some((g) => g.name === `分组 ${i}`)) i++
  profile.value.groups.push(newGroup(`分组 ${i}`))
}

function moveGroup(index: number, delta: number) {
  profile.value.groups = moveItem(profile.value.groups, index, delta)
}

function removeGroup(index: number) {
  const name = profile.value.groups[index].name
  const p = profile.value
  const refs =
    p.groups.filter((g) => g.members.some((m) => m.kind === 'group' && m.name === name)).length +
    p.rules.filter((r) => r.target === name).length +
    p.chains.filter((c) => c.via.kind === 'group' && c.via.name === name).length
  dialog.warning({
    title: '删除分组',
    content: refs
      ? `「${name}」仍被 ${refs} 处引用（分组成员 / 规则 / 链式代理），删除后需要修改这些引用，否则预览会报错。确定删除？`
      : `确定删除分组「${name}」？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: () => {
      profile.value.groups.splice(index, 1)
    },
  })
}

function addMember(index: number, m: Member) {
  const g = profile.value.groups[index]
  if (g.members.some((x) => sameMember(x, m))) {
    message.warning('该成员已在分组中')
    return
  }
  g.members.push(m)
}

function moveMember(index: number, mi: number, delta: number) {
  const g = profile.value.groups[index]
  g.members = moveItem(g.members, mi, delta)
}

function removeMember(index: number, mi: number) {
  profile.value.groups[index].members.splice(mi, 1)
}

function submitFilter(f: FilterMember) {
  if (filterFor.value !== null) addMember(filterFor.value, f)
  filterFor.value = null
}
</script>

<template>
  <NSpace vertical>
    <NEmpty v-if="!profile.groups.length" description="还没有分组：可以「套用模板」，或在下方新建" />
    <NCard v-for="(g, i) in profile.groups" :key="i" size="small" class="group" embedded>
      <template #header>
        <NSpace align="center">
          <NInput
            :value="drafts[i] ?? g.name"
            style="width: 200px"
            @update:value="(v: string) => (drafts[i] = v)"
            @blur="commitRename(i)"
            @keyup.enter="commitRename(i)"
          />
          <NSelect
            :value="g.type"
            :options="GROUP_TYPES"
            style="width: 130px"
            @update:value="(v: unknown) => (g.type = v as GroupType)"
          />
        </NSpace>
      </template>
      <template #header-extra>
        <NSpace size="small" :wrap="false">
          <NButton size="small" quaternary :disabled="i === 0" title="上移" @click="moveGroup(i, -1)">上移</NButton>
          <NButton size="small" quaternary :disabled="i === profile.groups.length - 1" title="下移" @click="moveGroup(i, 1)">下移</NButton>
          <NButton size="small" quaternary type="error" @click="removeGroup(i)">删除</NButton>
        </NSpace>
      </template>

      <div v-if="g.type !== 'select'" class="probe">
        <span class="edit-row__label">测速地址</span>
        <NInput v-model:value="g.url" size="small" class="mono" style="width: 300px" />
        <span class="edit-row__label">间隔</span>
        <NInputNumber
          :value="g.interval"
          :min="10"
          size="small"
          style="width: 110px"
          @update:value="(v: number | null) => (g.interval = v ?? 300)"
        >
          <template #suffix>秒</template>
        </NInputNumber>
        <template v-if="g.type === 'url-test'">
          <span class="edit-row__label">容差</span>
          <NInputNumber
            :value="g.tolerance"
            :min="0"
            size="small"
            style="width: 120px"
            @update:value="(v: number | null) => (g.tolerance = v ?? 50)"
          >
            <template #suffix>毫秒</template>
          </NInputNumber>
        </template>
      </div>

      <div v-for="(m, mi) in g.members" :key="mi" class="member">
        <span class="member__idx mono">{{ mi + 1 }}</span>
        <NTag size="small" :bordered="false" :type="tagType(m)">{{ memberLabel(m, nodeMap, sourceMap) }}</NTag>
        <NSpace size="small" class="member__ops" :wrap="false">
          <NButton size="tiny" quaternary @click="moveMember(i, mi, -1)">↑</NButton>
          <NButton size="tiny" quaternary @click="moveMember(i, mi, 1)">↓</NButton>
          <NButton size="tiny" quaternary type="error" @click="removeMember(i, mi)">✕</NButton>
        </NSpace>
      </div>
      <NText v-if="!g.members.length" depth="3" class="member-empty">暂无成员（空分组在生成配置时会自动加入 DIRECT）</NText>

      <NSpace class="adders" size="small">
        <NSelect
          :value="null"
          :options="nodeOptions"
          filterable
          placeholder="添加节点"
          size="small"
          style="width: 260px"
          @update:value="(v: unknown) => addMember(i, { kind: 'node', node_id: v as number })"
        />
        <NSelect
          :value="null"
          :options="groupOptions(g.name)"
          placeholder="添加分组"
          size="small"
          style="width: 160px"
          @update:value="(v: unknown) => addMember(i, { kind: 'group', name: v as string })"
        />
        <NButton size="small" secondary @click="addMember(i, { kind: 'builtin', name: 'DIRECT' })">+ DIRECT</NButton>
        <NButton size="small" secondary @click="addMember(i, { kind: 'builtin', name: 'REJECT' })">+ REJECT</NButton>
        <NButton size="small" secondary type="primary" @click="filterFor = i">+ 过滤器</NButton>
      </NSpace>
    </NCard>
    <NButton dashed block @click="addGroup">新建分组</NButton>
  </NSpace>

  <NModal
    :show="filterFor !== null"
    preset="card"
    title="添加过滤器（按名称动态匹配节点，机场更新后自动跟随）"
    style="width: 600px"
    @update:show="(v: boolean) => { if (!v) filterFor = null }"
  >
    <FilterForm :sources="sources" @submit="submitFilter" />
  </NModal>
</template>

<style scoped>
.group {
  border-radius: 10px;
}
.group + .group {
  margin-top: 4px;
}
.probe {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.member {
  align-items: center;
  border-radius: 6px;
  display: flex;
  gap: 10px;
  max-width: 620px;
  padding: 3px 4px;
}
.member:hover {
  background: #fff;
}
.member__idx {
  color: var(--rf-faint);
  text-align: right;
  width: 20px;
}
.member__ops {
  margin-left: auto;
  opacity: 0.35;
  transition: opacity 0.15s;
}
.member:hover .member__ops,
.member:focus-within .member__ops {
  opacity: 1;
}
.member-empty {
  display: block;
  padding: 4px 0;
}
.adders {
  border-top: 1px dashed var(--rf-line);
  margin-top: 10px;
  padding-top: 10px;
}
</style>
