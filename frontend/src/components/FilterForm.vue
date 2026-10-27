<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { NAlert, NButton, NForm, NFormItem, NInput, NSelect, NSpace, NTag } from 'naive-ui'
import { api } from '../api'
import type { FilterMember, NodeItem, Source } from '../api/types'

const props = defineProps<{ sources: Source[] }>()
const emit = defineEmits<{ submit: [filter: FilterMember] }>()

const form = reactive({ source_id: null as number | null, name_regex: '', exclude_regex: '' })
const matched = ref<NodeItem[] | null>(null)
const error = ref('')
const sourceOptions = computed(() => props.sources.map((s) => ({ label: s.name, value: s.id })))

function toFilter(): FilterMember {
  return { kind: 'filter', source_id: form.source_id, name_regex: form.name_regex, exclude_regex: form.exclude_regex || null }
}

async function test() {
  error.value = ''
  try {
    matched.value = await api.matchNodes({
      source_id: form.source_id, name_regex: form.name_regex, exclude_regex: form.exclude_regex || null,
    })
  } catch (e) {
    matched.value = null
    error.value = (e as Error).message
  }
}
</script>

<template>
  <NForm label-placement="left" label-width="96">
    <NFormItem label="节点源">
      <NSelect
        :value="form.source_id"
        :options="sourceOptions"
        clearable
        placeholder="全部节点源"
        @update:value="(v: unknown) => (form.source_id = (v as number | null) ?? null)"
      />
    </NFormItem>
    <NFormItem label="名称匹配">
      <NInput v-model:value="form.name_regex" class="mono" placeholder="正则，例如 香港|HK；留空匹配全部" />
    </NFormItem>
    <NFormItem label="排除">
      <NInput v-model:value="form.exclude_regex" class="mono" placeholder="正则，可选，例如 过期|剩余" />
    </NFormItem>
  </NForm>
  <NAlert v-if="error" type="error">{{ error }}</NAlert>
  <div v-if="matched" class="matched">
    <div class="matched__count">匹配到 <span class="mono">{{ matched.length }}</span> 个节点</div>
    <NTag v-for="n in matched.slice(0, 30)" :key="n.id" size="small" :bordered="false" style="margin: 2px">{{ n.name }}</NTag>
    <span v-if="matched.length > 30">…</span>
  </div>
  <NSpace justify="end" style="margin-top: 12px">
    <NButton @click="test">预览匹配</NButton>
    <NButton type="primary" @click="emit('submit', toFilter())">添加</NButton>
  </NSpace>
</template>

<style scoped>
.matched {
  background: var(--rf-canvas);
  border-radius: 8px;
  padding: 10px 12px;
}
.matched__count {
  color: var(--rf-muted);
  font-size: 13px;
  margin-bottom: 6px;
}
</style>
