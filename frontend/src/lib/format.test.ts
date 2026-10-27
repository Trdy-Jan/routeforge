import { describe, expect, it } from 'vitest'
import { formatBytes, formatEpoch, formatTime } from './format'

describe('format', () => {
  it('formats bytes', () => {
    expect(formatBytes(undefined)).toBe('—')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(10 * 1024 ** 3)).toBe('10.0 GB')
  })

  it('treats naive backend timestamps as UTC', () => {
    const expected = new Date('2026-01-01T00:00:00Z').toLocaleString('zh-CN', { hour12: false })
    expect(formatTime('2026-01-01T00:00:00')).toBe(expected)
    expect(formatTime('2026-01-01T00:00:00.123456')).toBe(expected)
    expect(formatTime(null)).toBe('—')
  })

  it('handles timezone-aware backend timestamps', () => {
    const expected = new Date('2026-01-01T00:00:00Z').toLocaleString('zh-CN', { hour12: false })
    expect(formatTime('2026-01-01T00:00:00+00:00')).toBe(expected)
    expect(formatTime('2026-01-01T00:00:00.123456Z')).toBe(expected)
  })

  it('formats epoch seconds as a date', () => {
    expect(formatEpoch(0)).toBe(new Date(0).toLocaleDateString('zh-CN'))
    expect(formatEpoch(undefined)).toBe('—')
  })
})
