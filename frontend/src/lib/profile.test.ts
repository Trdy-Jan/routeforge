import { describe, expect, it } from 'vitest'
import type { NodeItem, Profile, Source } from '../api/types'
import {
  insertBeforeMatch, memberLabel, moveItem, newGroup, newRule, renameGroup, moveRule, reorder, sameMember,
  maskedSubscriptionUrl, subscriptionUrl, targetOptions,
} from './profile'

const base: Profile = {
  name: 'p',
  groups: [
    { ...newGroup('节点选择'), members: [{ kind: 'group', name: '自动' }, { kind: 'builtin', name: 'DIRECT' }] },
    newGroup('自动'),
  ],
  rules: [
    { type: 'DOMAIN-SUFFIX', value: 'a.com', target: '自动', no_resolve: false },
    { type: 'MATCH', value: '', target: '节点选择', no_resolve: false },
  ],
  rule_providers: [],
  chains: [{ node: { kind: 'node', node_id: 1 }, via: { kind: 'group', name: '自动' } }],
}

describe('profile helpers', () => {
  it('renameGroup updates every reference', () => {
    const p = renameGroup(base, '自动', '自动测速')
    expect(p.groups.map((g) => g.name)).toEqual(['节点选择', '自动测速'])
    expect(p.groups[0].members[0]).toEqual({ kind: 'group', name: '自动测速' })
    expect(p.rules[0].target).toBe('自动测速')
    expect(p.chains[0].via).toEqual({ kind: 'group', name: '自动测速' })
    expect(base.groups[1].name).toBe('自动') // 不修改原对象
  })

  it('insertBeforeMatch keeps MATCH last', () => {
    const rules = insertBeforeMatch(base.rules, newRule('DIRECT'))
    expect(rules.map((r) => r.type)).toEqual(['DOMAIN-SUFFIX', 'DOMAIN-SUFFIX', 'MATCH'])
    expect(insertBeforeMatch([], newRule('DIRECT'))).toHaveLength(1)
  })

  it('moveItem swaps neighbours and ignores out-of-range moves', () => {
    expect(moveItem([1, 2, 3], 0, 1)).toEqual([2, 1, 3])
    expect(moveItem([1, 2, 3], 0, -1)).toEqual([1, 2, 3])
    expect(moveItem([1, 2, 3], 2, 1)).toEqual([1, 2, 3])
  })

  it('reorder moves an item to the target index', () => {
    expect(reorder([1, 2, 3, 4], 0, 2)).toEqual([2, 3, 1, 4])
    expect(reorder([1, 2, 3, 4], 3, 1)).toEqual([1, 4, 2, 3])
    expect(reorder([1, 2, 3], 1, 1)).toEqual([1, 2, 3])
    expect(reorder([1, 2, 3], 0, 5)).toEqual([1, 2, 3])
  })

  it('moveRule never moves MATCH or moves past it', () => {
    const rules = [newRule('a'), newRule('b'), { ...newRule('c'), type: 'MATCH' as const }]
    expect(moveRule(rules, 0, 1).map((r) => r.target)).toEqual(['b', 'a', 'c'])
    expect(moveRule(rules, 1, 2)).toBe(rules)
    expect(moveRule(rules, 2, 0)).toBe(rules)
  })

  it('sameMember compares by kind and identity', () => {
    expect(sameMember({ kind: 'node', node_id: 1 }, { kind: 'node', node_id: 1 })).toBe(true)
    expect(sameMember({ kind: 'node', node_id: 1 }, { kind: 'group', name: '1' })).toBe(false)
    const f = { kind: 'filter', source_id: null, name_regex: 'HK', exclude_regex: null } as const
    expect(sameMember(f, { ...f })).toBe(true)
    expect(sameMember(f, { ...f, exclude_regex: 'x' })).toBe(false)
  })

  it('memberLabel describes each member kind', () => {
    const nodes = new Map<number, NodeItem>([[1, { id: 1, name: '香港 01' } as NodeItem]])
    const sources = new Map<number, Source>([[2, { id: 2, name: '机场' } as Source]])
    expect(memberLabel({ kind: 'node', node_id: 1 }, nodes, sources)).toBe('香港 01')
    expect(memberLabel({ kind: 'node', node_id: 9 }, nodes, sources)).toBe('#9（已删除）')
    expect(memberLabel({ kind: 'group', name: '自动' }, nodes, sources)).toBe('分组：自动')
    expect(memberLabel({ kind: 'builtin', name: 'REJECT' }, nodes, sources)).toBe('REJECT')
    expect(memberLabel({ kind: 'filter', source_id: 2, name_regex: 'HK', exclude_regex: 'x0' }, nodes, sources))
      .toBe('过滤：机场 /HK/ 排除 /x0/')
    expect(memberLabel({ kind: 'filter', source_id: null, name_regex: '', exclude_regex: null }, nodes, sources))
      .toBe('过滤：全部节点源 /(全部)/')
  })

  it('targetOptions lists groups then builtins', () => {
    expect(targetOptions(base)).toEqual(['节点选择', '自动', 'DIRECT', 'REJECT'])
  })

  it('subscriptionUrl joins origin and token', () => {
    expect(subscriptionUrl('https://rf.example.com', 'abc')).toBe('https://rf.example.com/sub/abc')
  })

  it('maskedSubscriptionUrl hides the token but keeps the origin', () => {
    const masked = maskedSubscriptionUrl('https://rf.example.com', 'abcdef')
    expect(masked).toBe('https://rf.example.com/sub/••••••')
    expect(masked).not.toContain('abc')
    expect(maskedSubscriptionUrl('https://x', 'a'.repeat(40))).toBe(`https://x/sub/${'•'.repeat(16)}`)
  })
})
