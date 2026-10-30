<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NInput, NInputGroup, useMessage } from 'naive-ui'
import { copyText } from '../lib/clipboard'
import { maskedSubscriptionUrl, subscriptionUrl } from '../lib/profile'

const props = defineProps<{ token: string; size?: 'small' | 'medium' }>()
const message = useMessage()

// 默认隐藏 token，避免截图或旁人看到完整订阅链接
const revealed = ref(false)
const url = computed(() => subscriptionUrl(window.location.origin, props.token))
const shown = computed(() =>
  revealed.value ? url.value : maskedSubscriptionUrl(window.location.origin, props.token),
)

async function copy() {
  if (await copyText(url.value)) message.success('已复制订阅链接')
  else message.warning('无法访问剪贴板，请手动复制')
}
</script>

<template>
  <NInputGroup>
    <NInput :value="shown" readonly :size="size" class="mono">
      <template #suffix>
        <button
          type="button"
          class="eye"
          :aria-label="revealed ? '隐藏订阅链接' : '显示订阅链接'"
          :title="revealed ? '隐藏' : '显示'"
          @click="revealed = !revealed"
        >
          <svg v-if="revealed" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
          <svg v-else viewBox="0 0 24 24" aria-hidden="true">
            <path d="M10.6 5.1A10.8 10.8 0 0 1 12 5c6.5 0 10 7 10 7a17.6 17.6 0 0 1-2.6 3.6" />
            <path d="M6.6 6.6C3.7 8.5 2 12 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6" />
            <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
            <path d="m2 2 20 20" />
          </svg>
        </button>
      </template>
    </NInput>
    <NButton :size="size" :secondary="size === 'small'" type="primary" @click="copy">复制</NButton>
    <slot />
  </NInputGroup>
</template>

<style scoped>
.eye {
  align-items: center;
  background: none;
  border: 0;
  border-radius: 4px;
  color: var(--rf-muted);
  cursor: pointer;
  display: inline-flex;
  padding: 2px;
}
.eye:hover,
.eye:focus-visible {
  color: var(--rf-primary);
}
.eye svg {
  fill: none;
  height: 16px;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2;
  width: 16px;
}
</style>
