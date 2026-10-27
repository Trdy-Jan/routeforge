<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { NConfigProvider, NDialogProvider, NMessageProvider, dateZhCN, zhCN } from 'naive-ui'
import { api } from './api'
import BrandMark from './components/BrandMark.vue'
import { markLoggedOut } from './router'
import { themeOverrides } from './theme'

const route = useRoute()
const router = useRouter()

// 导航按使用顺序排成一条线路：节点源 → 节点 → 配置方案
const stations = computed(() =>
  router
    .getRoutes()
    .filter((r) => r.meta.title)
    .sort((a, b) => (a.meta.order ?? 0) - (b.meta.order ?? 0))
    .map((r) => ({ title: r.meta.title as string, name: String(r.name) })),
)
const activeKey = computed(() => route.meta.activeMenu ?? String(route.name ?? ''))
const showShell = computed(() => route.name !== 'login')

async function logout() {
  try {
    await api.logout()
  } finally {
    markLoggedOut()
    router.push({ name: 'login' })
  }
}
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN" :theme-overrides="themeOverrides">
    <NMessageProvider>
      <NDialogProvider>
        <div v-if="showShell" class="shell">
          <aside class="sider">
            <RouterLink to="/" class="brand">
              <BrandMark :size="30" />
              <span class="brand__name">RouteForge</span>
            </RouterLink>
            <nav class="line" aria-label="主导航">
              <RouterLink
                v-for="s in stations"
                :key="s.name"
                :to="{ name: s.name }"
                class="station"
                :class="{ 'station--active': activeKey === s.name }"
                :aria-current="activeKey === s.name ? 'page' : undefined"
                :title="s.title"
              >
                <span class="station__dot" />
                <span class="station__name">{{ s.title }}</span>
              </RouterLink>
            </nav>
            <button type="button" class="logout" @click="logout">退出登录</button>
          </aside>
          <main class="content">
            <div class="content__inner"><RouterView /></div>
          </main>
        </div>
        <RouterView v-else />
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100vh;
}

.sider {
  background: var(--rf-ink);
  color: var(--rf-ink-text);
  display: flex;
  flex: none;
  flex-direction: column;
  height: 100vh;
  padding: 22px 16px 18px;
  position: sticky;
  top: 0;
  width: 212px;
}

.brand {
  align-items: center;
  color: #fff;
  display: flex;
  gap: 10px;
  padding: 0 6px;
  text-decoration: none;
}
.brand__name {
  font-size: 17px;
  font-weight: 650;
  letter-spacing: 0.01em;
}

/* 线路：竖线贯穿所有站点 */
.line {
  margin-top: 40px;
  position: relative;
}
.line::before {
  background: var(--rf-ink-line);
  border-radius: 2px;
  bottom: 22px;
  content: "";
  left: 21px;
  position: absolute;
  top: 22px;
  width: 3px;
}

.station {
  align-items: center;
  border-radius: 8px;
  color: var(--rf-ink-text);
  display: flex;
  gap: 14px;
  height: 44px;
  margin-bottom: 6px;
  padding: 0 14px;
  position: relative;
  text-decoration: none;
  transition: background-color 0.15s, color 0.15s;
}
.station:hover {
  background: var(--rf-ink-2);
  color: #fff;
}
.station__dot {
  background: var(--rf-ink);
  border: 3px solid var(--rf-ink-line);
  border-radius: 50%;
  flex: none;
  height: 17px;
  position: relative;
  transition: border-color 0.15s, background-color 0.15s, box-shadow 0.15s;
  width: 17px;
}
.station:hover .station__dot {
  border-color: #8fa7bd;
}
.station__name {
  font-size: 15px;
}
.station--active {
  background: var(--rf-ink-2);
  color: #fff;
  font-weight: 600;
}
.station--active .station__dot {
  background: var(--rf-signal);
  border-color: #fff;
  box-shadow: 0 0 0 4px rgb(63 208 201 / 0.22);
}

.logout {
  background: none;
  border: 0;
  border-radius: 6px;
  color: #8fa7bd;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  margin-top: auto;
  padding: 8px 10px;
  text-align: left;
}
.logout:hover {
  background: var(--rf-ink-2);
  color: #fff;
}

.content {
  flex: 1;
  min-width: 0;
  padding: 32px 36px 48px;
}
.content__inner {
  margin: 0 auto;
  max-width: 1240px;
}

/* 窄屏：侧栏只保留站点圆点 */
@media (max-width: 860px) {
  .sider {
    padding: 18px 8px;
    width: 64px;
  }
  .brand {
    justify-content: center;
    padding: 0;
  }
  .brand__name,
  .station__name {
    display: none;
  }
  .line::before {
    left: 22px;
  }
  .station {
    justify-content: center;
    padding: 0;
  }
  .logout {
    font-size: 11px;
    padding: 6px 0;
    text-align: center;
    white-space: nowrap;
  }
  .content {
    padding: 20px 16px 40px;
  }
}
</style>
