<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<template>
  <!-- 网格布局：电脑上说明在标题下、操作在右侧底部对齐；手机上操作与标题同一行，说明占满下一行 -->
  <header class="page-header">
    <h1>{{ title }}</h1>
    <div v-if="$slots.default" class="page-header__actions"><slot /></div>
    <p v-if="description">{{ description }}</p>
  </header>
</template>

<style scoped>
.page-header {
  column-gap: 16px;
  display: grid;
  grid-template-areas:
    "title actions"
    "desc actions";
  grid-template-columns: minmax(0, 1fr) auto;
  margin-bottom: 20px;
}
h1 {
  font-size: 24px;
  font-weight: 650;
  grid-area: title;
  letter-spacing: 0.02em;
  line-height: 1.25;
  margin: 0;
}
p {
  color: var(--rf-muted);
  font-size: 14px;
  grid-area: desc;
  line-height: 1.6;
  margin: 6px 0 0;
  max-width: 72ch;
}
.page-header__actions {
  align-self: end;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  grid-area: actions;
}

@media (max-width: 640px) {
  .page-header {
    grid-template-areas:
      "title actions"
      "desc desc";
    margin-bottom: 16px;
  }
  h1 {
    align-self: center;
    font-size: 22px;
  }
  .page-header__actions {
    align-self: center;
  }
  p {
    font-size: 13px;
  }
}
</style>
