<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NCard, NForm, NFormItem, NInput } from 'naive-ui'
import { api } from '../api'
import { ApiError } from '../api/client'
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
    <NCard title="RouteForge 登录" style="width: 360px">
      <NForm @submit.prevent="submit">
        <NFormItem label="管理员密码">
          <NInput v-model:value="password" type="password" show-password-on="click" autofocus />
        </NFormItem>
        <NAlert v-if="error" type="error" style="margin-bottom: 12px">{{ error }}</NAlert>
        <NButton type="primary" attr-type="submit" block :loading="loading">登录</NButton>
      </NForm>
    </NCard>
  </div>
</template>

<style scoped>
.login {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
}
</style>
