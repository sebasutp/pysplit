import { execFileSync } from 'node:child_process'

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
    // Assert the interpolation mechanics, not the English fallback: the German
    // catalogue rewrites its single-brace placeholders on load.
    const rendered = i18n.t('Activity.expenseCreated', {
      expense: 'Abendessen',
      participant: 'Ada',
    })
    expect(rendered).toContain('Abendessen')
    expect(rendered).toContain('Ada')
    expect(rendered).not.toContain('{')
  })

  it('keeps every source i18n key present in en-US', () => {
    const cwd = globalThis.process?.cwd?.() || ''
    const script = `${cwd}/../scripts/check_i18n_keys.py`
    expect(() => execFileSync('python3', [script], { stdio: 'pipe' })).not.toThrow()
  })

  it('translates app-specific receipt and admin keys in the main locales', async () => {
    const english = {
      'ReceiptItems.title': 'Receipt items',
      'ReceiptItems.merchant': 'Merchant',
      'ReceiptItems.footer.reconciles': 'Reconciles',
      'SyncStatus.syncNow': 'Sync now',
      'Admin.title': 'Administration Dashboard',
    }

    for (const locale of ['de-DE', 'fr-FR', 'es', 'ja-JP']) {
      await setLocale(locale)
      for (const [key, source] of Object.entries(english)) {
        const translated = i18n.t(key)
        expect(translated, `${locale} ${key}`).not.toBe(source)
        expect(translated, `${locale} ${key}`).not.toBe(key)
        expect(translated.trim().length, `${locale} ${key}`).toBeGreaterThan(0)
      }
    }
  })

  it('preserves placeholders in machine-translated custom keys', async () => {
    for (const locale of ['de-DE', 'fr-FR', 'es', 'ja-JP']) {
      await setLocale(locale)

      const assigned = i18n.t('ReceiptItems.assign.description', { name: 'Ada' })
      expect(assigned, locale).toContain('Ada')
      expect(assigned, locale).not.toContain('{')

      const conflicts = i18n.t('SyncStatus.conflicts', { count: 3 })
      expect(conflicts, locale).toContain('3')
      expect(conflicts, locale).not.toContain('{')

      const remaining = i18n.t('ReceiptItems.item.remaining', { quantity: 2 })
      expect(remaining, locale).toContain('2')
      expect(remaining, locale).not.toContain('{')

      const offBy = i18n.t('ReceiptItems.footer.offBy', { amount: '$1.00' })
      expect(offBy, locale).toContain('$1.00')
      expect(offBy, locale).not.toContain('{')
    }
  })

  it('applies right-to-left direction for Arabic and restores LTR afterwards', async () => {
    await setLocale('ar')
    expect(document.documentElement.lang).toBe('ar')
    expect(document.documentElement.dir).toBe('rtl')

    await setLocale('de-DE')
    expect(document.documentElement.dir).toBe('ltr')
  })
})
