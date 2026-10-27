<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 28 })
</script>

<template>
  <!-- 一条线路在中途分叉：订阅转换 = 把节点分流到不同出口 -->
  <svg :width="size" :height="size" viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <rect width="32" height="32" rx="8" fill="#0A7B83" />
    <path d="M7 24 L13 16 C15 13 17 10 25 9" stroke="#fff" stroke-width="2.6" stroke-linecap="round" />
    <path d="M13 16 C15 19 18 22 25 23" stroke="#3FD0C9" stroke-width="2.6" stroke-linecap="round" />
    <circle cx="13" cy="16" r="3" fill="#fff" />
  </svg>
</template>
