import type { ImportItem, ParsedNode, ParseResult } from '../api/types'

/** 导入第 2 步表格中的一行：name 可被用户编辑，checked 表示是否导入。 */
export interface ImportRow {
  key: number
  node: ParsedNode
  name: string
  checked: boolean
}

/** 由解析结果生成勾选行：与已有节点或本批次更早的行同名的，默认不勾选。 */
export function buildRows(result: ParseResult): ImportRow[] {
  const seen = new Set(result.existing_names)
  return result.nodes.map((node, key) => {
    const name = node.name.trim()
    const checked = !seen.has(name)
    seen.add(name)
    return { key, node, name: node.name, checked }
  })
}

/** 当前名称下的重名行：与已有节点同名，或在本批次中出现不止一次。 */
export function duplicateKeys(rows: ImportRow[], existing: string[]): Set<number> {
  const existingSet = new Set(existing)
  const counts = new Map<string, number>()
  for (const r of rows) {
    const name = r.name.trim()
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  const dup = new Set<number>()
  for (const r of rows) {
    const name = r.name.trim()
    if (existingSet.has(name) || (counts.get(name) ?? 0) > 1) dup.add(r.key)
  }
  return dup
}

/** 改名时保留勾选状态：名称暂时为空的行只是不计入导入，不会被取消勾选。 */
export function renameRow(row: ImportRow, name: string): void {
  row.name = name
}

/** 勾选且名称非空的行，名称去首尾空格。 */
export function toImportItems(rows: ImportRow[]): ImportItem[] {
  return rows
    .filter((r) => r.checked && r.name.trim() !== '')
    .map((r) => ({ name: r.name.trim(), config: r.node.config }))
}

export function addressText(server: string, port: number, portRange: string | null | undefined): string {
  return `${server}:${portRange ?? port}`
}
