import type { Member, NodeItem, Profile, ProxyGroup, Rule, Source } from '../api/types'

export const BUILTIN_TARGETS = ['DIRECT', 'REJECT'] as const
export const DEFAULT_TEST_URL = 'https://www.gstatic.com/generate_204'

export function newGroup(name: string): ProxyGroup {
  return { name, type: 'select', members: [], url: DEFAULT_TEST_URL, interval: 300, tolerance: 50 }
}

export function newRule(target: string): Rule {
  return { type: 'DOMAIN-SUFFIX', value: '', target, no_resolve: false }
}

export function moveItem<T>(list: T[], index: number, delta: number): T[] {
  const to = index + delta
  if (to < 0 || to >= list.length) return list
  const copy = [...list]
  ;[copy[index], copy[to]] = [copy[to], copy[index]]
  return copy
}

export function reorder<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list
  const copy = [...list]
  const [item] = copy.splice(from, 1)
  copy.splice(to, 0, item)
  return copy
}

// MATCH 固定在最后：它自身不能移动，其他规则也不能越过它
export function moveRule(rules: Rule[], from: number, to: number): Rule[] {
  if (rules[from]?.type === 'MATCH' || rules[to]?.type === 'MATCH') return rules
  return reorder(rules, from, to)
}

export function insertBeforeMatch(rules: Rule[], rule: Rule): Rule[] {
  const at = rules.findIndex((r) => r.type === 'MATCH')
  if (at === -1) return [...rules, rule]
  return [...rules.slice(0, at), rule, ...rules.slice(at)]
}

export function sameMember(a: Member, b: Member): boolean {
  switch (a.kind) {
    case 'node':
      return b.kind === 'node' && a.node_id === b.node_id
    case 'group':
      return b.kind === 'group' && a.name === b.name
    case 'builtin':
      return b.kind === 'builtin' && a.name === b.name
    case 'filter':
      return (
        b.kind === 'filter' &&
        a.source_id === b.source_id &&
        a.name_regex === b.name_regex &&
        (a.exclude_regex || null) === (b.exclude_regex || null)
      )
  }
}

export function memberLabel(m: Member, nodes: Map<number, NodeItem>, sources: Map<number, Source>): string {
  switch (m.kind) {
    case 'node':
      return nodes.get(m.node_id)?.name ?? `#${m.node_id}（已删除）`
    case 'group':
      return `分组：${m.name}`
    case 'builtin':
      return m.name
    case 'filter': {
      const src = m.source_id == null ? '全部节点源' : (sources.get(m.source_id)?.name ?? `#${m.source_id}`)
      const exclude = m.exclude_regex ? ` 排除 /${m.exclude_regex}/` : ''
      return `过滤：${src} /${m.name_regex || '(全部)'}/${exclude}`
    }
  }
}

export function renameGroup(profile: Profile, from: string, to: string): Profile {
  const rename = (m: Member): Member => (m.kind === 'group' && m.name === from ? { ...m, name: to } : m)
  return {
    ...profile,
    groups: profile.groups.map((g) => ({ ...g, name: g.name === from ? to : g.name, members: g.members.map(rename) })),
    rules: profile.rules.map((r) => (r.target === from ? { ...r, target: to } : r)),
    chains: profile.chains.map((c) =>
      c.via.kind === 'group' && c.via.name === from ? { ...c, via: { kind: 'group', name: to } } : c,
    ),
  }
}

export function targetOptions(profile: Profile): string[] {
  return [...profile.groups.map((g) => g.name), ...BUILTIN_TARGETS]
}

export function subscriptionUrl(origin: string, token: string): string {
  return `${origin}/sub/${token}`
}

export function maskedSubscriptionUrl(origin: string, token: string): string {
  return subscriptionUrl(origin, '•'.repeat(Math.min(token.length, 16)))
}
