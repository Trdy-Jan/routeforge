import type { GlobalThemeOverrides } from 'naive-ui'

// 与 styles.css 中的 --rf-* 变量保持一致
const sans =
  '"Segoe UI Variable Text", "Segoe UI", "PingFang SC", "HarmonyOS Sans SC", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif'
const mono = '"JetBrains Mono", "Cascadia Mono", "SF Mono", Consolas, "Microsoft YaHei UI", monospace'

export const themeOverrides: GlobalThemeOverrides = {
  common: {
    fontFamily: sans,
    fontFamilyMono: mono,
    primaryColor: '#0a7b83',
    primaryColorHover: '#0c8f98',
    primaryColorPressed: '#08656c',
    primaryColorSuppl: '#0c8f98',
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
    borderRadius: '6px',
  },
}
