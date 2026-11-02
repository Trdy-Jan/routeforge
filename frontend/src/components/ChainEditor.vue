<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NEmpty, NRadioButton, NRadioGroup, NSelect, NSpace } from 'naive-ui'
import type { Chain, NodeItem, Profile, Source } from '../api/types'
import { nodeLabel } from '../lib/profile'

const profile = defineModel<Profile>({ required: true })
const props = defineProps<{ nodes: NodeItem[]; sources: Source[] }>()

const sourceMap = computed(() => new Map(props.sources.map((s) => [s.id, s])))
const nodeOptions = computed(() => props.nodes.map((n) => ({ label: nodeLabel(n, sourceMap.value), value: n.id })))
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
    <p class="hint">
      落地节点经由「前置」（分组或节点）出站，生成的配置中为 Mihomo 的 <code class="mono">dialer-proxy</code>。
      落地节点本身需要出现在某个分组里才会生效，且前置不能包含该落地节点。
    </p>
    <NEmpty v-if="!profile.chains.length" description="还没有链式代理" />
    <div v-for="(c, i) in profile.chains" :key="i" class="edit-row">
      <span class="edit-row__label ch-label">落地节点</span>
      <NSelect
        :value="c.node.node_id"
        :options="nodeOptions"
        filterable
        class="ch-select ch-node"
        @update:value="(v: unknown) => (c.node = { kind: 'node', node_id: v as number })"
      />
      <span class="edit-row__label ch-label ch-via-label">经由</span>
      <NRadioGroup class="ch-via-kind" :value="c.via.kind" @update:value="(v: unknown) => setViaKind(c, v as 'group' | 'node')">
        <NRadioButton value="group">分组</NRadioButton>
        <NRadioButton value="node">节点</NRadioButton>
      </NRadioGroup>
      <NSelect
        :value="c.via.kind === 'group' ? c.via.name : c.via.node_id"
        :options="c.via.kind === 'group' ? groupOptions : nodeOptions"
        filterable
        class="ch-select ch-via"
        @update:value="(v: unknown) => setVia(c, v)"
      />
      <NButton size="tiny" quaternary type="error" class="ch-remove" @click="remove(i)">✕</NButton>
    </div>
    <NButton dashed block :disabled="!canAdd" @click="add">添加链式代理</NButton>
  </NSpace>
</template>

<style scoped>
.ch-select {
  width: 240px;
}
.hint {
  color: var(--rf-muted);
  font-size: 13px;
  line-height: 1.7;
  margin: 0 0 4px;
}
.hint code {
  white-space: nowrap;
}

/* 手机：落地节点（标签 + 删除）一行、选择框一行；经由同理 */
@media (max-width: 640px) {
  .edit-row {
    border: 1px solid var(--rf-line);
    border-radius: 10px;
    margin-bottom: 8px;
    padding: 10px;
  }
  .edit-row:last-of-type {
    border-bottom: 1px solid var(--rf-line);
  }
  .ch-label {
    order: 1;
  }
  .ch-remove {
    margin-left: auto;
    order: 2;
  }
  .ch-node {
    flex-basis: 100%;
    order: 3;
    width: auto;
  }
  .ch-via-label {
    order: 4;
  }
  .ch-via-kind {
    order: 5;
  }
  .ch-via {
    flex-basis: 100%;
    order: 6;
    width: auto;
  }
}
</style>
