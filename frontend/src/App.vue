<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import {
  NButton, NConfigProvider, NDialogProvider, NLayout, NLayoutContent, NLayoutSider, NMenu, NMessageProvider,
  dateZhCN, zhCN, type MenuOption,
} from 'naive-ui'
import { api } from './api'
import { markLoggedOut } from './router'

const route = useRoute()
const router = useRouter()

const menuOptions = computed<MenuOption[]>(() =>
  router
    .getRoutes()
    .filter((r) => r.meta.title)
    .sort((a, b) => (a.meta.order ?? 0) - (b.meta.order ?? 0))
    .map((r) => ({ label: r.meta.title, key: String(r.name) })),
)
const activeKey = computed(() => route.meta.activeMenu ?? String(route.name ?? ''))
const showShell = computed(() => route.name !== 'login')

function navigate(key: string) {
  router.push({ name: key })
}

async function logout() {
  await api.logout()
  markLoggedOut()
  router.push({ name: 'login' })
}
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN">
    <NMessageProvider>
      <NDialogProvider>
        <NLayout v-if="showShell" has-sider class="shell">
          <NLayoutSider bordered :width="180">
            <div class="brand">RouteForge</div>
            <NMenu :options="menuOptions" :value="activeKey" @update:value="navigate" />
            <div class="logout"><NButton text @click="logout">退出登录</NButton></div>
          </NLayoutSider>
          <NLayoutContent content-style="padding: 24px;">
            <RouterView />
          </NLayoutContent>
        </NLayout>
        <RouterView v-else />
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style>
body {
  margin: 0;
}
.shell {
  height: 100vh;
}
.brand {
  font-size: 18px;
  font-weight: 600;
  padding: 16px;
}
.logout {
  padding: 16px;
}
</style>
