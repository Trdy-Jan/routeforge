import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { api } from './api'
import LoginView from './views/LoginView.vue'
import SourcesView from './views/SourcesView.vue'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    order?: number
    activeMenu?: string
  }
}

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: LoginView },
  { path: '/', redirect: { name: 'sources' } },
  { path: '/sources', name: 'sources', component: SourcesView, meta: { title: '节点源', order: 1 } },
]

export const router = createRouter({ history: createWebHistory(), routes })

let authenticated = false
let authCheckInFlight = false

export function isAuthCheckInFlight(): boolean {
  return authCheckInFlight
}

export function markLoggedIn(): void {
  authenticated = true
}

export function markLoggedOut(): void {
  authenticated = false
}

router.beforeEach(async (to) => {
  if (to.name === 'login' || authenticated) return true
  authCheckInFlight = true
  try {
    await api.me()
    authenticated = true
    return true
  } catch {
    return { name: 'login', query: { redirect: to.fullPath } }
  } finally {
    authCheckInFlight = false
  }
})
