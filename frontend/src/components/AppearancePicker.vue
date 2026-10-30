<script setup lang="ts">
import { NPopover, NRadioButton, NRadioGroup } from 'naive-ui'
import { ACCENTS, appearance, isDark } from '../lib/appearance'

const modes = [
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
  { value: 'system', label: '跟随系统' },
] as const
</script>

<template>
  <NPopover trigger="click" placement="right-end" :show-arrow="false">
    <template #trigger>
      <button type="button" class="trigger" title="外观">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <circle cx="8" cy="8" r="6.2" stroke="currentColor" stroke-width="1.6" />
          <path d="M8 1.8 A6.2 6.2 0 0 1 8 14.2 Z" fill="currentColor" />
        </svg>
        <span class="trigger__label">外观</span>
      </button>
    </template>
    <div class="panel">
      <div class="panel__title">主题</div>
      <NRadioGroup v-model:value="appearance.mode" size="small">
        <NRadioButton v-for="m in modes" :key="m.value" :value="m.value">{{ m.label }}</NRadioButton>
      </NRadioGroup>
      <div class="panel__title">主题色</div>
      <div class="swatches" role="radiogroup" aria-label="主题色">
        <button
          v-for="a in ACCENTS"
          :key="a.key"
          type="button"
          role="radio"
          class="swatch"
          :class="{ 'swatch--active': appearance.accent === a.key }"
          :aria-checked="appearance.accent === a.key"
          :title="a.label"
          :style="{ '--c': isDark ? a.dark : a.light }"
          @click="appearance.accent = a.key"
        />
      </div>
    </div>
  </NPopover>
</template>

<style scoped>
.trigger {
  align-items: center;
  background: none;
  border: 0;
  border-radius: 6px;
  color: #8fa7bd;
  cursor: pointer;
  display: flex;
  font: inherit;
  font-size: 13px;
  gap: 8px;
  padding: 8px 10px;
  text-align: left;
  width: 100%;
}
.trigger:hover {
  background: var(--rf-ink-2);
  color: #fff;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 2px;
}
.panel__title {
  color: var(--rf-muted);
  font-size: 12px;
}
.panel__title:not(:first-child) {
  margin-top: 6px;
}

.swatches {
  display: flex;
  gap: 10px;
}
.swatch {
  background: var(--c);
  border: 0;
  border-radius: 50%;
  cursor: pointer;
  height: 22px;
  padding: 0;
  transition: box-shadow 0.15s;
  width: 22px;
}
.swatch:hover {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--c) 25%, transparent);
}
.swatch--active {
  box-shadow: 0 0 0 2px var(--rf-surface), 0 0 0 4px var(--c);
}

@media (max-width: 860px) {
  .trigger {
    justify-content: center;
    padding: 8px 0;
  }
  .trigger__label {
    display: none;
  }
}
</style>
