<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <header class="page-header">
    <div class="page-header__text">
      <h1>{{ title }}</h1>
      <p v-if="description">{{ description }}</p>
    </div>
    <div v-if="$slots.default" class="page-header__actions"><slot /></div>
  </header>
</template>

<style scoped>
.page-header {
  align-items: flex-end;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  justify-content: space-between;
  margin-bottom: 20px;
}
h1 {
  font-size: 24px;
  font-weight: 650;
  letter-spacing: 0.02em;
  line-height: 1.25;
  margin: 0;
}
p {
  color: var(--rf-muted);
  font-size: 14px;
  line-height: 1.6;
  margin: 6px 0 0;
  max-width: 72ch;
}
.page-header__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
