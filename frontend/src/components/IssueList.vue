<script setup lang="ts">
import { NButton } from 'naive-ui'
import type { Issue, IssueSection } from '../api/types'

defineProps<{ issues: Issue[] }>()
const emit = defineEmits<{ goto: [section: IssueSection] }>()

const SECTION_LABELS: Record<IssueSection, string> = {
  groups: '分组',
  rules: '规则',
  providers: '规则集',
  chains: '链式代理',
}
</script>

<template>
  <ul class="issues">
    <li v-for="(issue, i) in issues" :key="i" class="issue">
      <span class="issue__tag">{{ SECTION_LABELS[issue.section] }}</span>
      <div class="issue__body">
        <div class="issue__msg">{{ issue.message }}</div>
        <div class="issue__hint">修复建议：{{ issue.hint }}</div>
      </div>
      <NButton size="tiny" secondary type="error" class="issue__go" @click="emit('goto', issue.section)">
        前往修改
      </NButton>
    </li>
  </ul>
</template>

<style scoped>
.issues {
  display: flex;
  flex-direction: column;
  gap: 8px;
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
}
.issue {
  align-items: flex-start;
  display: flex;
  gap: 10px;
}
.issue__tag {
  background: var(--rf-error);
  border-radius: 4px;
  color: #fff;
  flex-shrink: 0;
  font-size: 12px;
  line-height: 20px;
  padding: 0 6px;
}
.issue__body {
  flex: 1;
  min-width: 0;
}
.issue__msg {
  font-weight: 600;
  overflow-wrap: anywhere;
}
.issue__hint {
  color: var(--rf-muted);
  font-size: 13px;
  margin-top: 2px;
}
.issue__go {
  flex-shrink: 0;
}
</style>
