import type { GlobalThemeOverrides } from 'naive-ui'
import { mix } from './lib/appearance'

// 与 styles.css 中的 --rf-* 变量保持一致
const sans =
  '"Segoe UI Variable Text", "Segoe UI", "PingFang SC", "HarmonyOS Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif'
const mono = '"JetBrains Mono", "Cascadia Mono", "SF Mono", Consolas, "Microsoft YaHei UI", monospace'

const LIGHT = {
  canvas: '#f6f6f7',
  surface: '#ffffff',
  line: '#e4e4e8',
  lineSoft: '#efeff2',
  text: '#17171a',
  muted: '#5c5c66',
  faint: '#9a9aa4',
  success: '#15803d',
  warning: '#b45309',
  error: '#dc2626',
}

const DARK = {
  canvas: '#0f0f11',
  surface: '#17171a',
  raised: '#1d1d21',
  line: '#2a2a2f',
  lineSoft: '#212125',
  text: '#ececef',
  muted: '#a0a0aa',
  faint: '#6e6e78',
  success: '#4ade80',
  warning: '#fbbf24',
  error: '#f87171',
}

/** 提示框：淡底 + 同色细边框，避免整块浓色 */
function alertOverrides(dark: boolean, primary: string, c: { success: string; warning: string; error: string }) {
  const tone = (color: string) => ({
    color: dark ? `${color}14` : mix(color, '#ffffff', 0.93),
    border: `1px solid ${dark ? `${color}40` : mix(color, '#ffffff', 0.7)}`,
  })
  const [info, success, warning, error] = [primary, c.success, c.warning, c.error].map(tone)
  return {
    colorInfo: info.color,
    borderInfo: info.border,
    colorSuccess: success.color,
    borderSuccess: success.border,
    colorWarning: warning.color,
    borderWarning: warning.border,
    colorError: error.color,
    borderError: error.border,
  }
}

export function buildThemeOverrides(dark: boolean, primary: string): GlobalThemeOverrides {
  const hover = dark ? mix(primary, '#ffffff', 0.14) : mix(primary, '#ffffff', 0.12)
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
    const c = DARK
    return {
      common: {
        ...base,
        infoColor: primary,
        successColor: c.success,
        warningColor: c.warning,
        errorColor: c.error,
        textColorBase: c.text,
        textColor1: c.text,
        textColor2: c.text,
        textColor3: c.muted,
        placeholderColor: c.faint,
        bodyColor: c.canvas,
        cardColor: c.surface,
        modalColor: c.raised,
        popoverColor: c.raised,
        tableColor: c.surface,
        tableHeaderColor: '#1b1b1f',
        hoverColor: 'rgba(255, 255, 255, 0.06)',
        inputColor: 'rgba(255, 255, 255, 0.05)',
        borderColor: c.line,
        dividerColor: c.line,
      },
      Card: { borderRadius: '10px' },
      DataTable: { thColor: '#1b1b1f', tdColorHover: '#1c1c20', borderColor: c.lineSoft },
      Alert: alertOverrides(true, primary, c),
    }
  }
  const c = LIGHT
  return {
    common: {
      ...base,
      infoColor: primary,
      successColor: c.success,
      warningColor: c.warning,
      errorColor: c.error,
      textColorBase: c.text,
      textColor1: c.text,
      textColor2: c.text,
      textColor3: c.muted,
      placeholderColor: c.faint,
      bodyColor: c.canvas,
      cardColor: c.surface,
      tableHeaderColor: '#fafafb',
      hoverColor: c.lineSoft,
      borderColor: c.line,
      dividerColor: c.line,
    },
    Card: { borderRadius: '10px' },
    DataTable: { thColor: '#fafafb', tdColorHover: '#fafafb', borderColor: c.lineSoft },
    Alert: alertOverrides(false, primary, c),
  }
}
