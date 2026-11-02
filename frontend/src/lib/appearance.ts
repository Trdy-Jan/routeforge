import { computed, reactive, watchEffect } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

export interface Accent {
  key: string
  label: string
  /** 浅色主题下的主色 */
  light: string
  /** 深色主题下的主色（更亮，保证在深底上的对比度） */
  dark: string
  /** 高亮色：当前站点、品牌标记的分叉线 */
  signal: string
}

// 浅色用较深的色阶（白字按钮对比度 ≥ 4.5），深色用较亮的色阶（配深色按钮文字）
export const ACCENTS: Accent[] = [
  { key: 'teal', label: '青', light: '#0f766e', dark: '#2dd4bf', signal: '#5eead4' },
  { key: 'blue', label: '蓝', light: '#2563eb', dark: '#60a5fa', signal: '#93c5fd' },
  { key: 'violet', label: '紫', light: '#6d28d9', dark: '#a78bfa', signal: '#c4b5fd' },
  { key: 'green', label: '绿', light: '#15803d', dark: '#4ade80', signal: '#86efac' },
  { key: 'orange', label: '橙', light: '#c2410c', dark: '#fb923c', signal: '#fdba74' },
  { key: 'rose', label: '玫红', light: '#be123c', dark: '#fb7185', signal: '#fda4af' },
]

export const STORAGE_KEY = 'rf-appearance'

interface Stored {
  mode: ThemeMode
  accent: string
}

function load(): Stored {
  const fallback: Stored = { mode: 'system', accent: ACCENTS[0].key }
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null')
    if (!raw || typeof raw !== 'object') return fallback
    return {
      mode: ['light', 'dark', 'system'].includes(raw.mode) ? raw.mode : fallback.mode,
      accent: ACCENTS.some((a) => a.key === raw.accent) ? raw.accent : fallback.accent,
    }
  } catch {
    return fallback
  }
}

const media = typeof window !== 'undefined' ? window.matchMedia?.('(prefers-color-scheme: dark)') : undefined

export const appearance = reactive({ ...load(), systemDark: media?.matches ?? false })

media?.addEventListener('change', (e) => {
  appearance.systemDark = e.matches
})

export const isDark = computed(() =>
  appearance.mode === 'system' ? appearance.systemDark : appearance.mode === 'dark',
)

export const accent = computed(() => ACCENTS.find((a) => a.key === appearance.accent) ?? ACCENTS[0])

export const primaryColor = computed(() => (isDark.value ? accent.value.dark : accent.value.light))

/** 把 hex 颜色按比例混向另一颜色，用于生成悬停 / 按下态 */
export function mix(hex: string, target: string, amount: number): string {
  const parse = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16))
  const a = parse(hex)
  const b = parse(target)
  return (
    '#' +
    a
      .map((v, i) => Math.round(v + (b[i] - v) * amount))
      .map((v) => v.toString(16).padStart(2, '0'))
      .join('')
  )
}

/** 同步到 <html>：data-theme 驱动 styles.css 中的深色变量，主色通过内联变量下发 */
export function installAppearance() {
  watchEffect(() => {
    const root = document.documentElement
    root.dataset.theme = isDark.value ? 'dark' : 'light'
    root.style.colorScheme = isDark.value ? 'dark' : 'light'
    root.style.setProperty('--rf-primary', primaryColor.value)
    root.style.setProperty('--rf-signal', accent.value.signal)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode: appearance.mode, accent: appearance.accent }))
    } catch {
      // 隐私模式等场景下不可写，忽略即可
    }
  })
}
