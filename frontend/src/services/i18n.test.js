import { afterEach, describe, expect, it } from 'vitest'

import i18n, {
  SUPPORTED_LOCALES,
  getLocale,
  matchLocale,
  normalizeMessages,
  setLocale,
} from './i18n'

afterEach(async () => {
  await setLocale('en-US')
  localStorage.clear()
  document.cookie = 'NEXT_LOCALE=; Path=/; Max-Age=0'
})

describe('i18n', () => {
  it('lists every locale with en-US first and bundled eagerly', () => {
    expect(SUPPORTED_LOCALES).toHaveLength(35)
    expect(SUPPORTED_LOCALES[0]).toBe('en-US')
    expect(i18n.hasResourceBundle('en-US', 'translation')).toBe(true)
    // The other catalogues are dynamic imports and must not be in the entry.
    expect(i18n.hasResourceBundle('de-DE', 'translation')).toBe(false)
  })

  it('imports the catalogue when the language changes', async () => {
    await expect(setLocale('de-DE')).resolves.toBe('de-DE')

    expect(i18n.hasResourceBundle('de-DE', 'translation')).toBe(true)
    expect(i18n.t('Groups.myGroups')).toBe('Meine Gruppen')
    expect(getLocale()).toBe('de-DE')
    expect(document.documentElement.lang).toBe('de-DE')
    expect(localStorage.getItem('pysplit-locale')).toBe('de-DE')
    expect(document.cookie).toContain('NEXT_LOCALE=de-DE')
  })

  it('matches browser tags to the bundled locale codes', () => {
    expect(matchLocale('de_DE')).toBe('de-DE')
    expect(matchLocale('fr-CA')).toBe('fr-FR')
    expect(matchLocale('zh-TW')).toBe('zh-TW')
    expect(matchLocale('xx')).toBeNull()
  })

  it('interpolates ported single-brace placeholders', () => {
    expect(i18n.t('ReceiptItems.footer.offBy', { amount: '$1.00' })).toBe('Off by $1.00')
    expect(i18n.t('ReceiptItems.item.quantity', { assigned: '1', total: '3' })).toBe('1 of 3')
    expect(i18n.t('ReceiptItems.assign.description', { name: 'Ada' })).toBe(
      'Choose who pays for “Ada”.',
    )
    expect(i18n.t('ReceiptItems.applyConfirm.total', { current: '1', new: '2' })).toBe(
      'total 1 → 2',
    )
  })

  it('rewrites single braces but leaves existing double braces untouched', () => {
    expect(normalizeMessages('{assigned} of {total}')).toBe('{{assigned}} of {{total}}')
    expect(normalizeMessages('Off by {{amount}}')).toBe('Off by {{amount}}')
    expect(normalizeMessages('literal {not a placeholder} and {1bad}')).toBe(
      'literal {not a placeholder} and {1bad}',
    )
    expect(normalizeMessages({ nested: ['{name}', 3, null, { deep: '{amount}' }] })).toEqual({
      nested: ['{{name}}', 3, null, { deep: '{{amount}}' }],
    })
  })

  it('normalises a dynamically loaded non-English catalogue', async () => {
    i18n.removeResourceBundle('de-DE', 'translation')

    await setLocale('de-DE')

    expect(i18n.hasResourceBundle('de-DE', 'translation')).toBe(true)
    expect(i18n.t('ReceiptItems.item.quantity', { assigned: '1', total: '2' })).toBe('1 of 2')
  })
})
