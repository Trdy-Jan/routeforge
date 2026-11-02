import { describe, expect, it } from 'vitest'
import type { LibraryItem, Profile, Rule } from '../api/types'
import { newGroup } from './profile'
import { addLibraryRule, canUseGeoRule, searchLibrary } from './ruleLibrary'

const BASE = 'https://github.com/MetaCubeX/meta-rules-dat/raw/meta'
const openai: LibraryItem = { category: 'geosite', name: 'openai', behavior: 'domain', url: `${BASE}/geo/geosite/openai.mrs` }
const openaiExtra: LibraryItem = { ...openai, name: 'openai-extra', url: `${BASE}/geo/geosite/openai-extra.mrs` }
const aiNotCn: LibraryItem = {
  category: 'geosite', name: 'category-ai-!cn', behavior: 'domain', url: `${BASE}/geo/geosite/category-ai-!cn.mrs`,
}
const tg: LibraryItem = { category: 'geoip', name: 'telegram', behavior: 'ipcidr', url: `${BASE}/geo/geoip/telegram.mrs` }
const apple: LibraryItem = { category: 'geo-lite', name: 'apple', behavior: 'domain', url: `${BASE}/geo-lite/geosite/apple.mrs` }

const MATCH: Rule = { type: 'MATCH', value: '', values: [], target: '节点选择', no_resolve: false }

function profile(over: Partial<Profile> = {}): Profile {
  return {
    name: 'p',
    groups: ['AI', 'TG', 'X', 'Y', 'Z', '节点选择'].map(newGroup),
    rules: [{ type: 'DOMAIN-SUFFIX', value: '', values: ['a.com'], target: 'DIRECT', no_resolve: false }, { ...MATCH }],
    rule_providers: [],
    chains: [],
    ...over,
  }
}

describe('searchLibrary', () => {
  const items = [aiNotCn, openaiExtra, openai, tg, apple]

  it('ranks exact > prefix > contains and filters category', () => {
    expect(searchLibrary(items, 'geosite', 'openai').map((i) => i.name)).toEqual(['openai', 'openai-extra'])
    expect(searchLibrary(items, 'geosite', 'ai').map((i) => i.name)).toEqual(['category-ai-!cn', 'openai', 'openai-extra'])
    expect(searchLibrary(items, 'geoip', 'openai')).toEqual([])
  })

  it('returns whole category alphabetically for empty query', () => {
    expect(searchLibrary(items, 'geosite', '  ').map((i) => i.name)).toEqual(['category-ai-!cn', 'openai', 'openai-extra'])
  })

  it('search is case-insensitive', () => {
    expect(searchLibrary(items, 'geosite', 'OpenAI')[0]).toBe(openai)
  })
})

describe('addLibraryRule', () => {
  it('rule-set mode creates provider and inserts before MATCH', () => {
    const r = addLibraryRule(profile(), openai, 'rule-set', 'AI')
    expect(r.status).toBe('added')
    expect(r.profile.rule_providers).toEqual([
      { name: 'geosite-openai', behavior: 'domain', format: 'mrs', url: openai.url, interval: 86400 },
    ])
    expect(r.index).toBe(1)
    expect(r.target).toBe('AI')
    expect(r.profile.rules[1]).toEqual({ type: 'RULE-SET', value: 'geosite-openai', values: [], target: 'AI', no_resolve: false })
    expect(r.profile.rules.at(-1)?.type).toBe('MATCH')
  })

  it('reuses provider created by template', () => {
    const p = profile({ rule_providers: [{ name: 'category-ai-not-cn', behavior: 'domain', format: 'mrs', url: aiNotCn.url, interval: 86400 }] })
    const r = addLibraryRule(p, aiNotCn, 'rule-set', 'AI')
    expect(r.status).toBe('added')
    expect(r.profile.rule_providers).toHaveLength(1)
    expect(r.profile.rules[r.index].value).toBe('category-ai-not-cn')
  })

  it('suffixes name on conflict', () => {
    const p = profile({
      rule_providers: [
        { name: 'geosite-openai', behavior: 'domain', format: 'mrs', url: 'https://other/x.mrs', interval: 86400 },
        { name: 'geosite-openai-2', behavior: 'domain', format: 'mrs', url: 'https://other/y.mrs', interval: 86400 },
      ],
    })
    const r = addLibraryRule(p, openai, 'rule-set', 'AI')
    expect(r.profile.rule_providers.at(-1)?.name).toBe('geosite-openai-3')
  })

  it('geoip defaults no_resolve and geo mode', () => {
    const geo = addLibraryRule(profile(), tg, 'geo', 'TG')
    expect(geo.profile.rules[geo.index]).toEqual({ type: 'GEOIP', value: 'telegram', values: [], target: 'TG', no_resolve: true })
    expect(geo.profile.rule_providers).toEqual([])
    const set = addLibraryRule(profile(), tg, 'rule-set', 'TG')
    expect(set.profile.rule_providers[0]).toMatchObject({ name: 'geoip-telegram', behavior: 'ipcidr' })
    expect(set.profile.rules[set.index].no_resolve).toBe(true)
  })

  it('geosite geo mode inserts GEOSITE rule', () => {
    const r = addLibraryRule(profile(), openai, 'geo', 'AI')
    expect(r.profile.rules[r.index]).toEqual({ type: 'GEOSITE', value: 'openai', values: [], target: 'AI', no_resolve: false })
  })

  it('geo-lite cannot use geo mode', () => {
    expect(canUseGeoRule(apple)).toBe(false)
    expect(canUseGeoRule(openai)).toBe(true)
    expect(() => addLibraryRule(profile(), apple, 'geo', 'X')).toThrow()
    const r = addLibraryRule(profile(), apple, 'rule-set', 'X')
    expect(r.profile.rule_providers[0].name).toBe('geolite-apple')
  })

  it('skips duplicate and reports existing rule', () => {
    const p = profile({
      rules: [{ type: 'GEOSITE', value: 'OpenAI', values: [], target: 'X', no_resolve: false }, { ...MATCH }],
    })
    const r = addLibraryRule(p, openai, 'rule-set', 'Y')
    expect(r).toEqual({ profile: p, status: 'exists', index: 0, target: 'X' })

    const p2 = profile({
      rule_providers: [{ name: 'tg', behavior: 'ipcidr', format: 'mrs', url: tg.url, interval: 86400 }],
      rules: [{ ...MATCH }, { type: 'RULE-SET', value: 'tg', values: [], target: 'Z', no_resolve: true }],
    })
    const r2 = addLibraryRule(p2, tg, 'geo', 'Y')
    expect(r2.status).toBe('exists')
    expect(r2.index).toBe(1)
    expect(r2.target).toBe('Z')
  })

  it('rejects a target that is not a group or builtin of the profile', () => {
    const p = profile({ groups: [{ name: 'A', type: 'select', members: [], url: '', interval: 300, tolerance: 50 }] })
    expect(() => addLibraryRule(p, openai, 'rule-set', 'B-group')).toThrow('目标分组「B-group」不存在')
    expect(addLibraryRule(p, openai, 'rule-set', 'A').status).toBe('added')
    expect(addLibraryRule(p, openai, 'rule-set', 'DIRECT').status).toBe('added')
  })

  it('appends when there is no MATCH', () => {
    const p = profile({ rules: [] })
    const r = addLibraryRule(p, openai, 'rule-set', 'DIRECT')
    expect(r.index).toBe(0)
    expect(r.profile.rules).toHaveLength(1)
  })

  it('does not mutate input', () => {
    const p = profile()
    const snapshot = JSON.stringify(p)
    addLibraryRule(p, openai, 'rule-set', 'AI')
    expect(JSON.stringify(p)).toBe(snapshot)
  })
})
