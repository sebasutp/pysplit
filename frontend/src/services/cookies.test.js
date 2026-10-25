import { afterEach, describe, expect, it } from 'vitest'

import { readCookie } from './cookies'

afterEach(() => {
  document.cookie = 'pysplit_csrf=; Path=/; Max-Age=0'
  document.cookie = 'NEXT_LOCALE=; Path=/; Max-Age=0'
})

describe('readCookie', () => {
  it('returns null when the cookie is absent', () => {
    expect(readCookie('pysplit_csrf')).toBeNull()
  })

  it('reads and URI-decodes a cookie value', () => {
    document.cookie = 'pysplit_csrf=abc%2F123; Path=/'
    expect(readCookie('pysplit_csrf')).toBe('abc/123')
  })

  it('ignores cookies with other names and empty parts', () => {
    document.cookie = 'NEXT_LOCALE=de-DE; Path=/'
    expect(readCookie('pysplit_csrf')).toBeNull()
    expect(readCookie('NEXT_LOCALE')).toBe('de-DE')
  })
})
