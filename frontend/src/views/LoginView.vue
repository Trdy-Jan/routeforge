<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NForm, NFormItem, NInput } from 'naive-ui'
import { api } from '../api'
import { ApiError } from '../api/client'
import BrandMark from '../components/BrandMark.vue'
import { cookieNotSavedHint } from '../lib/session'
import { markLoggedIn } from '../router'

const route = useRoute()
const router = useRouter()
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  loading.value = true
  error.value = ''
  try {
    await api.login(password.value)
    try {
      await api.me()
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        error.value = cookieNotSavedHint(window.location.protocol)
        return
      }
      throw e
    }
    markLoggedIn()
    const raw = route.query.redirect
    const redirect = typeof raw === 'string' && /^\/(?!\/)/.test(raw) ? raw : '/'
    router.push(redirect)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login">
    <svg class="login__map" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <g fill="none" stroke-width="4" stroke-linecap="round">
        <path d="M-20 620 H300 C360 620 380 600 420 560 L560 420 C600 380 620 360 680 360 H1220" stroke="#25496d" />
        <path d="M560 420 C600 460 620 480 680 480 H900 C960 480 980 500 1020 540 L1220 740" class="map-accent" />
        <path d="M-20 180 H220 C280 180 300 200 340 240 L420 320 C460 360 480 360 540 360 H680" stroke="#25496d" />
      </g>
      <g class="map-stops" stroke-width="4">
        <circle cx="300" cy="620" r="9" stroke="#25496d" />
        <circle cx="560" cy="420" r="11" class="map-signal" />
        <circle cx="900" cy="480" r="9" class="map-accent" />
        <circle cx="220" cy="180" r="9" stroke="#25496d" />
        <circle cx="680" cy="360" r="9" stroke="#25496d" />
      </g>
    </svg>
    <main class="panel">
      <div class="panel__brand">
        <BrandMark :size="40" />
        <div>
          <h1>RouteForge</h1>
          <p>节点、规则与订阅管理</p>
        </div>
      </div>
      <NForm @submit.prevent="submit">
        <NFormItem label="管理员密码" :show-feedback="false" style="margin-bottom: 16px">
          <NInput v-model:value="password" type="password" size="large" show-password-on="click" autofocus />
        </NFormItem>
        <NAlert v-if="error" type="error" style="margin-bottom: 16px">{{ error }}</NAlert>
        <NButton type="primary" size="large" attr-type="submit" block :loading="loading" :disabled="!password">
          登录
        </NButton>
      </NForm>
    </main>
  </div>
</template>

<style scoped>
.login {
  align-items: center;
  background: var(--rf-ink);
  display: flex;
  justify-content: center;
  min-height: 100vh;
  overflow: hidden;
  padding: 24px 16px;
  position: relative;
}
.login__map {
  height: 100%;
  inset: 0;
  position: absolute;
  width: 100%;
}
.map-accent {
  stroke: color-mix(in srgb, var(--rf-primary) 55%, var(--rf-ink));
}
.map-signal {
  stroke: var(--rf-signal);
}
.map-stops {
  fill: var(--rf-ink);
}
.panel {
  background: var(--rf-surface);
  border-radius: 14px;
  box-shadow: 0 24px 60px -20px rgb(4 18 33 / 0.6);
  max-width: 380px;
  padding: 32px 32px 28px;
  position: relative;
  width: 100%;
}
.panel__brand {
  align-items: center;
  display: flex;
  gap: 14px;
  margin-bottom: 28px;
}
h1 {
  font-size: 22px;
  font-weight: 650;
  line-height: 1.2;
  margin: 0;
}
p {
  color: var(--rf-muted);
  font-size: 13px;
  margin: 4px 0 0;
}
</style>
