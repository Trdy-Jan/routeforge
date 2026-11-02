import { describe, expect, it } from 'vitest'
import type { ParsedNode } from '../api/types'
import { addressText, buildRows, duplicateKeys, renameRow, toImportItems } from './nodeImport'

const n = (name: string, over: Partial<ParsedNode> = {}): ParsedNode =>
  ({ name, type: 'mieru', server: '203.0.113.10', port: 1, port_range: null, config: { name }, ...over })

describe('buildRows', () => {
  it('unchecks names that exist or repeat within the batch', () => {
    const rows = buildRows({ nodes: [n('A'), n('B'), n('A')], errors: [], existing_names: ['B'] })
    expect(rows.map((r) => r.checked)).toEqual([true, false, false])
  })
})

describe('duplicateKeys', () => {
  it('updates after rename and ignores surrounding spaces', () => {
    const rows = buildRows({ nodes: [n('A'), n('A')], errors: [], existing_names: [] })
    expect([...duplicateKeys(rows, [])]).toEqual([rows[0].key, rows[1].key])
    rows[1].name = 'A2'
    expect(duplicateKeys(rows, []).size).toBe(0)
    rows[1].name = ' A '
    expect(duplicateKeys(rows, []).size).toBe(2)
  })

  it('flags names that already exist in the source', () => {
    const rows = buildRows({ nodes: [n('A'), n('B')], errors: [], existing_names: ['B'] })
    expect([...duplicateKeys(rows, ['B'])]).toEqual([rows[1].key])
  })
})

describe('toImportItems', () => {
  it('skips blank names and unchecked rows, trims names', () => {
    const rows = buildRows({ nodes: [n('A'), n('B'), n('C')], errors: [], existing_names: [] })
    rows[0].name = '  香港  '
    rows[1].name = '   '
    rows[2].checked = false
    expect(toImportItems(rows)).toEqual([{ name: '香港', config: { name: 'A' } }])
  })
})

it('addressText prefers port range', () => {
  expect(addressText('h', 2090, '2090-2099')).toBe('h:2090-2099')
  expect(addressText('h', 443, null)).toBe('h:443')
})

describe('renameRow', () => {
  it('keeps the row checked when the name is cleared and retyped', () => {
    const [row] = buildRows({ nodes: [n('A')], errors: [], existing_names: [] })
    renameRow(row, '')
    expect(toImportItems([row])).toEqual([])
    renameRow(row, '香港 Mieru')
    expect(row.checked).toBe(true)
    expect(toImportItems([row])).toEqual([{ name: '香港 Mieru', config: { name: 'A' } }])
  })
})
