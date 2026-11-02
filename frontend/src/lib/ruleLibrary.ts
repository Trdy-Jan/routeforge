import type { LibraryCategory, LibraryItem, Profile, Rule, RuleProvider, RuleType } from '../api/types'
import { insertBeforeMatch } from './profile'

export const LIBRARY_CATEGORIES: { value: LibraryCategory; label: string }[] = [
  { value: 'geosite', label: 'geosite' },
  { value: 'geoip', label: 'geoip' },
  { value: 'geo-lite', label: 'geo-lite' },
]

const PROVIDER_PREFIX: Record<LibraryCategory, string> = { geosite: 'geosite-', geoip: 'geoip-', 'geo-lite': 'geolite-' }

/** 按分类过滤并排序：完全匹配 > 前缀匹配 > 包含匹配，同档按名字字母序；不区分大小写。 */
export function searchLibrary(items: LibraryItem[], category: LibraryCategory, query: string): LibraryItem[] {
  const q = query.trim().toLowerCase()
  const ranked: { item: LibraryItem; rank: number }[] = []
  for (const item of items) {
    if (item.category !== category) continue
    const name = item.name.toLowerCase()
    const rank = !q ? 0 : name === q ? 0 : name.startsWith(q) ? 1 : name.includes(q) ? 2 : -1
    if (rank >= 0) ranked.push({ item, rank })
  }
  ranked.sort((a, b) => a.rank - b.rank || (a.item.name < b.item.name ? -1 : a.item.name > b.item.name ? 1 : 0))
  return ranked.map((r) => r.item)
}

/** geo-lite 是精简规则，客户端自带的 geodata 里不一定有，只能以规则集方式加入。 */
export function canUseGeoRule(item: LibraryItem): boolean {
  return item.category !== 'geo-lite'
}

export type AddMode = 'rule-set' | 'geo'

export interface AddResult {
  profile: Profile
  status: 'added' | 'exists'
  /** 新增或已存在规则的下标（0 基） */
  index: number
  /** 该规则的目标 */
  target: string
}

function geoType(item: LibraryItem): RuleType {
  return item.category === 'geoip' ? 'GEOIP' : 'GEOSITE'
}

function findExisting(profile: Profile, item: LibraryItem): number {
  const providerNames = new Set(profile.rule_providers.filter((p) => p.url === item.url).map((p) => p.name))
  const type = canUseGeoRule(item) ? geoType(item) : null
  const name = item.name.toLowerCase()
  return profile.rules.findIndex(
    (r) =>
      (r.type === 'RULE-SET' && providerNames.has(r.value)) ||
      (type !== null && r.type === type && r.value.toLowerCase() === name),
  )
}

function uniqueName(base: string, taken: Set<string>): string {
  let name = base
  for (let n = 2; taken.has(name); n++) name = `${base}-${n}`
  return name
}

/** 把规则库条目加入方案；同一条规则已存在时不修改方案并返回已有位置。不修改入参。 */
export function addLibraryRule(profile: Profile, item: LibraryItem, mode: AddMode, target: string): AddResult {
  if (mode === 'geo' && !canUseGeoRule(item)) throw new Error('精简规则只能以规则集方式加入')
  const existing = findExisting(profile, item)
  if (existing !== -1) return { profile, status: 'exists', index: existing, target: profile.rules[existing].target }

  let providers = profile.rule_providers
  let rule: Rule
  const noResolve = item.category === 'geoip'
  if (mode === 'rule-set') {
    let provider = providers.find((p) => p.url === item.url)
    if (!provider) {
      const name = uniqueName(PROVIDER_PREFIX[item.category] + item.name, new Set(providers.map((p) => p.name)))
      provider = { name, behavior: item.behavior, format: 'mrs', url: item.url, interval: 86400 } satisfies RuleProvider
      providers = [...providers, provider]
    }
    rule = { type: 'RULE-SET', value: provider.name, values: [], target, no_resolve: noResolve }
  } else {
    rule = { type: geoType(item), value: item.name, values: [], target, no_resolve: noResolve }
  }
  const rules = insertBeforeMatch(profile.rules, rule)
  return { profile: { ...profile, rules, rule_providers: providers }, status: 'added', index: rules.indexOf(rule), target }
}
