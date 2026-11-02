<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { NConfigProvider, NDialogProvider, NMessageProvider, darkTheme, dateZhCN, zhCN } from 'naive-ui'
import { api } from './api'
import AppearancePicker from './components/AppearancePicker.vue'
import BrandMark from './components/BrandMark.vue'
import { isDark, primaryColor } from './lib/appearance'
import { isMobile } from './lib/viewport'
import { markLoggedOut } from './router'
import { buildThemeOverrides } from './theme'

const theme = computed(() => (isDark.value ? darkTheme : null))
const themeOverrides = computed(() => buildThemeOverrides(isDark.value, primaryColor.value))

const route = useRoute()
const router = useRouter()

// 底部标签栏的图标（24×24 线框，按路由名对应）
const ICONS: Record<string, string[]> = {
  sources: ['M12 3 3 7.5l9 4.5 9-4.5L12 3Z', 'm3 12 9 4.5 9-4.5', 'm3 16.5 9 4.5 9-4.5'],
  nodes: [
    'M12 7.5v4', 'M12 11.5 6.5 16', 'M12 11.5l5.5 4.5',
    'M14.5 5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0Z',
    'M8 18a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0Z',
    'M21 18a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0Z',
  ],
  profiles: ['M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z', 'M14 3v5h5', 'M9 13h6', 'M9 17h4'],
  'rule-library': ['M4 19V5a2 2 0 0 1 2-2h14v14H6a2 2 0 0 0-2 2Zm0 0a2 2 0 0 0 2 2h14v-4', 'M9 7h7', 'M9 11h5'],
  settings: [
    'M4 7h9', 'M18 7h2', 'M4 17h3', 'M12 17h8',
    'M17.5 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z', 'M11.5 17a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z',
  ],
}

// 导航按使用顺序排列：节点源 → 节点 → 配置方案
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
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN" :theme="theme" :theme-overrides="themeOverrides">
    <NMessageProvider>
      <NDialogProvider>
        <div v-if="showShell" class="shell">
          <header class="topbar">
            <div class="topbar__inner">
              <RouterLink to="/" class="brand">
                <BrandMark :size="26" />
                <span class="brand__name">RouteForge</span>
              </RouterLink>
              <nav class="tabs" aria-label="主导航">
                <RouterLink
                  v-for="s in stations"
                  :key="s.name"
                  :to="{ name: s.name }"
                  class="tab"
                  :class="{ 'tab--active': activeKey === s.name }"
                  :aria-current="activeKey === s.name ? 'page' : undefined"
                >
                  {{ s.title }}
                </RouterLink>
              </nav>
              <div class="tools">
                <!-- 手机：退出登录收进菜单，不占顶栏位置 -->
                <AppearancePicker v-if="isMobile" variant="menu">
                  <button type="button" class="menu-item menu-item--danger" @click="logout">退出登录</button>
                </AppearancePicker>
                <template v-else>
                  <AppearancePicker />
                  <span class="tools__sep" aria-hidden="true" />
                  <button type="button" class="logout" @click="logout">退出登录</button>
                </template>
              </div>
            </div>
          </header>
          <main class="content">
            <div class="content__inner"><RouterView /></div>
          </main>
          <!-- 手机：主导航移到屏幕底部，拇指可达 -->
          <nav class="bottombar" aria-label="主导航">
            <RouterLink
              v-for="s in stations"
              :key="s.name"
              :to="{ name: s.name }"
              class="bottomtab"
              :class="{ 'bottomtab--active': activeKey === s.name }"
              :aria-current="activeKey === s.name ? 'page' : undefined"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path v-for="(d, i) in ICONS[s.name] ?? []" :key="i" :d="d" />
              </svg>
              <span>{{ s.title }}</span>
            </RouterLink>
          </nav>
        </div>
        <RouterView v-else />
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

/* 顶栏：与页面同色的半透明栏，滚动时内容在下方模糊透出 */
.topbar {
  -webkit-backdrop-filter: saturate(180%) blur(12px);
  backdrop-filter: saturate(180%) blur(12px);
  background: color-mix(in srgb, var(--rf-surface) 82%, transparent);
  border-bottom: 1px solid var(--rf-line);
  flex: none;
  position: sticky;
  top: 0;
  z-index: 10;
}
.topbar__inner {
  align-items: center;
  display: flex;
  height: 56px;
  margin: 0 auto;
  max-width: 1312px;
  padding: 0 36px;
}

.brand {
  align-items: center;
  border-radius: 6px;
  color: var(--rf-text);
  display: flex;
  flex: none;
  gap: 9px;
  margin-right: 28px;
  text-decoration: none;
}
.brand__name {
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.tabs {
  align-items: center;
  align-self: stretch;
  display: flex;
  gap: 2px;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}
.tabs::-webkit-scrollbar {
  display: none;
}

.tab {
  align-items: center;
  align-self: stretch;
  color: var(--rf-muted);
  display: flex;
  flex: none;
  font-size: 14px;
  padding: 0 12px;
  position: relative;
  text-decoration: none;
  z-index: 0;
}
/* 悬停底色画在伪元素上，下划线才能贴住顶栏底边 */
.tab::before {
  border-radius: 6px;
  content: "";
  inset: 12px 0;
  position: absolute;
  transition: background-color 0.12s;
  z-index: -1;
}
.tab:hover {
  color: var(--rf-text);
}
.tab:hover::before {
  background: var(--rf-line-soft);
}
.tab--active {
  color: var(--rf-text);
  font-weight: 600;
}
.tab--active::after {
  background: var(--rf-primary);
  border-radius: 2px 2px 0 0;
  bottom: -1px;
  content: "";
  height: 2px;
  left: 12px;
  position: absolute;
  right: 12px;
}
.tab:focus-visible {
  outline: none;
}
.tab:focus-visible::before {
  outline: 2px solid var(--rf-primary);
  outline-offset: -2px;
}

.tools {
  align-items: center;
  display: flex;
  flex: none;
  gap: 6px;
  margin-left: auto;
  padding-left: 16px;
}
.tools__sep {
  background: var(--rf-line);
  height: 18px;
  width: 1px;
}

.logout {
  background: none;
  border: 0;
  border-radius: 6px;
  color: var(--rf-muted);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  height: 32px;
  padding: 0 10px;
  white-space: nowrap;
}
.logout:hover {
  background: var(--rf-line-soft);
  color: var(--rf-text);
}

.menu-item {
  background: none;
  border: 0;
  border-radius: 6px;
  cursor: pointer;
  font: inherit;
  font-size: 14px;
  padding: 8px 6px;
  text-align: left;
  width: 100%;
}
.menu-item--danger {
  color: var(--rf-error);
}
.menu-item:hover {
  background: var(--rf-line-soft);
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

@media (max-width: 860px) {
  .topbar__inner {
    padding: 0 12px 0 16px;
  }
  .brand {
    margin-right: 8px;
  }
  .tab {
    padding: 0 9px;
  }
  .tab--active::after {
    left: 9px;
    right: 9px;
  }
  .tools {
    padding-left: 8px;
  }
  .content {
    padding: 24px 20px 40px;
  }
}

.bottombar {
  display: none;
}

/* 手机：顶栏只留品牌与工具，导航放到底部标签栏 */
@media (max-width: 640px) {
  .topbar__inner {
    height: 52px;
  }
  .tabs {
    display: none;
  }
  .content {
    padding: 16px 12px calc(76px + env(safe-area-inset-bottom));
  }

  .bottombar {
    -webkit-backdrop-filter: saturate(180%) blur(12px);
    backdrop-filter: saturate(180%) blur(12px);
    background: color-mix(in srgb, var(--rf-surface) 88%, transparent);
    border-top: 1px solid var(--rf-line);
    bottom: 0;
    display: flex;
    left: 0;
    padding-bottom: env(safe-area-inset-bottom);
    position: fixed;
    right: 0;
    z-index: 10;
  }
  .bottomtab {
    align-items: center;
    color: var(--rf-faint);
    display: flex;
    flex: 1;
    flex-direction: column;
    font-size: 11px;
    gap: 3px;
    height: 56px;
    justify-content: center;
    min-width: 0;
    text-decoration: none;
    -webkit-tap-highlight-color: transparent;
  }
  .bottomtab svg {
    fill: none;
    height: 22px;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.7;
    width: 22px;
  }
  .bottomtab span {
    white-space: nowrap;
  }
  .bottomtab--active {
    color: var(--rf-primary);
    font-weight: 600;
  }
  .bottomtab--active svg {
    stroke-width: 2;
  }
  .bottomtab:focus-visible {
    outline-offset: -4px;
  }
}
</style>
