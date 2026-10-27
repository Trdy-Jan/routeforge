import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { api } from './api'
import LoginView from './views/LoginView.vue'
import SourcesView from './views/SourcesView.vue'
import NodesView from './views/NodesView.vue'
import ProfileEditView from './views/ProfileEditView.vue'
import ProfilesView from './views/ProfilesView.vue'

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
  { path: '/nodes', name: 'nodes', component: NodesView, meta: { title: '节点', order: 2 } },
  { path: '/profiles', name: 'profiles', component: ProfilesView, meta: { title: '配置方案', order: 3 } },
  {
    path: '/profiles/:id',
    name: 'profile-edit',
    component: ProfileEditView,
    props: (route) => ({ id: Number(route.params.id) }),
    meta: { activeMenu: 'profiles' },
  },
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
