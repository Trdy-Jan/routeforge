import { createApp } from 'vue'
import App from './App.vue'
import './styles.css'
import { setUnauthorizedHandler } from './api/client'
import { installAppearance } from './lib/appearance'
import { isAuthCheckInFlight, markLoggedOut, router } from './router'

installAppearance()

setUnauthorizedHandler(() => {
  markLoggedOut()
  if (isAuthCheckInFlight()) return
  const current = router.currentRoute.value
  if (current.name !== 'login') {
    router.push({ name: 'login', query: { redirect: current.fullPath } })
  }
})

createApp(App).use(router).mount('#app')
