import { ref } from 'vue'

/** 手机布局断点：与 styles.css 中的 640px 保持一致 */
export const MOBILE_QUERY = '(max-width: 640px)'

const media = typeof window !== 'undefined' ? window.matchMedia?.(MOBILE_QUERY) : undefined

/** 当前是否为手机宽度；全局共享一个监听 */
export const isMobile = ref(media?.matches ?? false)

media?.addEventListener('change', (e) => {
  isMobile.value = e.matches
})
