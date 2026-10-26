const UNITS = ['B', 'KB', 'MB', 'GB', 'TB']

export function formatBytes(n: number | null | undefined): string {
  if (n == null) return '—'
  let value = n
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit++
  }
  return `${unit === 0 ? value : value.toFixed(1)} ${UNITS[unit]}`
}

/** 后端发送带时区的 UTC 时间（Z 或 +00:00，可能带 6 位微秒）；不带时区的字符串仍按 UTC 处理。 */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const trimmed = iso.replace(/(\.\d{3})\d+/, '$1')
  const hasZone = /([zZ]|[+-]\d{2}:\d{2})$/.test(trimmed)
  return new Date(hasZone ? trimmed : `${trimmed}Z`).toLocaleString('zh-CN', { hour12: false })
}

export function formatEpoch(seconds: number | null | undefined): string {
  if (seconds == null) return '—'
  return new Date(seconds * 1000).toLocaleDateString('zh-CN')
}
