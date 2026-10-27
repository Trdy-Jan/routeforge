import { describe, expect, it } from 'vitest'
import { cookieNotSavedHint } from './session'

describe('cookieNotSavedHint', () => {
  it('points at ROUTEFORGE_COOKIE_SECURE over plain HTTP', () => {
    const hint = cookieNotSavedHint('http:')
    expect(hint).toContain('HTTP')
    expect(hint).toContain('ROUTEFORGE_COOKIE_SECURE')
  })

  it('gives a generic cookie hint over HTTPS', () => {
    const hint = cookieNotSavedHint('https:')
    expect(hint).not.toContain('ROUTEFORGE_COOKIE_SECURE')
    expect(hint).toContain('cookie')
  })
})
