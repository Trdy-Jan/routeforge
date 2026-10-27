<script setup lang="ts">
import { computed } from 'vue'
import { NAlert, NButton, NEmpty, NRadioButton, NRadioGroup, NSelect, NSpace } from 'naive-ui'
import type { Chain, NodeItem, Profile } from '../api/types'

const profile = defineModel<Profile>({ required: true })
const props = defineProps<{ nodes: NodeItem[] }>()

const nodeOptions = computed(() => props.nodes.map((n) => ({ label: n.name, value: n.id })))
const groupOptions = computed(() => profile.value.groups.map((g) => ({ label: g.name, value: g.name })))
const canAdd = computed(() => props.nodes.length > 0 && profile.value.groups.length > 0)

function add() {
  profile.value.chains.push({
    node: { kind: 'node', node_id: props.nodes[0].id },
    via: { kind: 'group', name: profile.value.groups[0].name },
  })
}

function setViaKind(c: Chain, kind: 'group' | 'node') {
  if (kind === c.via.kind) return
  c.via = kind === 'group'
    ? { kind: 'group', name: profile.value.groups[0]?.name ?? '' }
    : { kind: 'node', node_id: props.nodes[0]?.id ?? 0 }
}

function setVia(c: Chain, value: unknown) {
  c.via = c.via.kind === 'group' ? { kind: 'group', name: value as string } : { kind: 'node', node_id: value as number }
}

function remove(i: number) {
  profile.value.chains.splice(i, 1)
}
</script>

<template>
  <NSpace vertical>
    <NAlert type="info">
      链式代理：落地节点经由「前置」（分组或节点）出站，生成的配置中为 Mihomo 的 dialer-proxy。
      落地节点本身需要出现在某个分组里才会生效，且前置不能包含该落地节点。
    </NAlert>
    <NEmpty v-if="!profile.chains.length" description="还没有链式代理" />
    <div v-for="(c, i) in profile.chains" :key="i" class="row">
      <span>落地节点</span>
      <NSelect
        :value="c.node.node_id"
        :options="nodeOptions"
        filterable
        style="width: 240px"
        @update:value="(v: unknown) => (c.node = { kind: 'node', node_id: v as number })"
      />
      <span>经由</span>
      <NRadioGroup :value="c.via.kind" @update:value="(v: unknown) => setViaKind(c, v as 'group' | 'node')">
        <NRadioButton value="group">分组</NRadioButton>
        <NRadioButton value="node">节点</NRadioButton>
      </NRadioGroup>
      <NSelect
        :value="c.via.kind === 'group' ? c.via.name : c.via.node_id"
        :options="c.via.kind === 'group' ? groupOptions : nodeOptions"
        filterable
        style="width: 240px"
        @update:value="(v: unknown) => setVia(c, v)"
      />
      <NButton size="tiny" quaternary type="error" @click="remove(i)">✕</NButton>
    </div>
    <NButton dashed block :disabled="!canAdd" @click="add">添加链式代理</NButton>
  </NSpace>
</template>

<style scoped>
.row {
  align-items: center;
  display: flex;
  gap: 8px;
}
</style>
