import type { GlobalThemeOverrides } from 'naive-ui'
import { mix } from './lib/appearance'

// 与 styles.css 中的 --rf-* 变量保持一致
const sans =
  '"Segoe UI Variable Text", "Segoe UI", "PingFang SC", "HarmonyOS Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif'
const mono = '"JetBrains Mono", "Cascadia Mono", "SF Mono", Consolas, "Microsoft YaHei UI", monospace'

export function buildThemeOverrides(dark: boolean, primary: string): GlobalThemeOverrides {
  const hover = dark ? mix(primary, '#ffffff', 0.12) : mix(primary, '#ffffff', 0.1)
  const pressed = mix(primary, '#000000', 0.15)
  const base = {
    fontFamily: sans,
    fontFamilyMono: mono,
    primaryColor: primary,
    primaryColorHover: hover,
    primaryColorPressed: pressed,
    primaryColorSuppl: hover,
    borderRadius: '6px',
  }
  if (dark) {
    return {
      common: {
        ...base,
        successColor: '#4fb879',
        warningColor: '#e0a33a',
        errorColor: '#e5677a',
        textColorBase: '#e2e8ee',
        textColor2: '#e2e8ee',
        textColor3: '#9aa7b4',
        placeholderColor: '#6f7c89',
        bodyColor: '#0f141a',
        cardColor: '#182029',
        modalColor: '#1c252f',
        popoverColor: '#1f2933',
        tableColor: '#182029',
        borderColor: '#2a3541',
        dividerColor: '#2a3541',
      },
    }
  }
  return {
    common: {
      ...base,
      infoColor: '#1f4366',
      successColor: '#2f8f57',
      warningColor: '#c9820a',
      errorColor: '#c8384b',
      textColorBase: '#1c2733',
      textColor2: '#1c2733',
      textColor3: '#5e6b78',
      placeholderColor: '#8a96a3',
      bodyColor: '#eef2f5',
      borderColor: '#dce3ea',
      dividerColor: '#dce3ea',
    },
  }
}
