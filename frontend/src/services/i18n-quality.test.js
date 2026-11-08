import { afterEach, describe, expect, it } from 'vitest'

import { GROUP_TABS } from '../components/groups/GroupHeader'
import { RECURRENCES } from '../components/expenses/ExpenseBasicsCard'
import { THEME_OPTIONS } from '../components/system/ThemeToggle'
import dynamicFamilies from '../locales/dynamic-families.json'
import enUS from '../locales/messages/en-US.json'
import { DATE_GROUP_KEYS } from '../utils/date-groups'
import { STATS_RANGES } from '../utils/stats-range'
import i18n, { setLocale } from './i18n'

const catalogues = import.meta.glob('../locales/messages/*.json', {
  eager: true,
  import: 'default',
})

/** @param {unknown} value @param {string} [prefix] @returns {Record<string, unknown>} */
function flatten(value, prefix = '') {
  if (!value || typeof value !== 'object') return { [prefix]: value }
  /** @type {Record<string, unknown>} */
  const result = {}
  for (const [key, child] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key
    Object.assign(result, flatten(child, path))
  }
  return result
}

const enKeys = new Set(Object.keys(flatten(enUS)))

const EXPECTED_ACTIONS = {
  'de-DE': {
    'Theme.light': 'Hell',
    'Theme.dark': 'Dunkel',
    'Pwa.dismiss': 'Schließen',
    'Expenses.search': 'Ausgaben durchsuchen',
    'Expenses.loading': 'Ausgaben werden geladen…',
    'SyncStatus.retryFailed': 'Fehlgeschlagene Änderungen erneut versuchen',
    'SyncStatus.discardFailed': 'Fehlgeschlagene Änderungen verwerfen',
    'SyncStatus.keepMine': 'Meine Version behalten',
    'Pending.expense': 'Synchronisierung ausstehend',
  },
  'fr-FR': {
    'Theme.light': 'Clair',
    'Theme.dark': 'Sombre',
    'Pwa.dismiss': 'Fermer',
    'Expenses.search': 'Rechercher des dépenses',
    'Expenses.loading': 'Chargement des dépenses…',
    'SyncStatus.retryFailed': 'Réessayer les modifications échouées',
    'SyncStatus.discardFailed': 'Ignorer les modifications échouées',
    'SyncStatus.keepMine': 'Conserver ma version',
    'Pending.expense': 'Synchronisation en attente',
  },
  es: {
    'Theme.light': 'Claro',
    'Theme.dark': 'Oscuro',
    'Pwa.dismiss': 'Cerrar',
    'Expenses.search': 'Buscar gastos',
    'Expenses.loading': 'Cargando gastos…',
    'SyncStatus.retryFailed': 'Reintentar cambios fallidos',
    'SyncStatus.discardFailed': 'Descartar cambios fallidos',
    'SyncStatus.keepMine': 'Conservar mi versión',
    'Pending.expense': 'Sincronización pendiente',
  },
  ar: {
    'Theme.light': 'فاتح',
    'Theme.dark': 'داكن',
    'Pwa.dismiss': 'إغلاق',
    'Expenses.search': 'البحث في النفقات',
    'Expenses.loading': 'جارٍ تحميل النفقات…',
    'SyncStatus.retryFailed': 'إعادة محاولة التغييرات الفاشلة',
    'SyncStatus.discardFailed': 'تجاهل التغييرات الفاشلة',
    'SyncStatus.keepMine': 'الاحتفاظ بنسختي',
    'Pending.expense': 'في انتظار المزامنة',
  },
  'ja-JP': {
    'Theme.light': 'ライト',
    'Theme.dark': 'ダーク',
    'Pwa.dismiss': '閉じる',
    'Expenses.search': '経費を検索',
    'Expenses.loading': '経費を読み込み中…',
    'SyncStatus.retryFailed': '失敗した変更を再試行',
    'SyncStatus.discardFailed': '失敗した変更を破棄',
    'SyncStatus.keepMine': '自分の変更を保持',
    'Pending.expense': '同期待ち',
  },
}

afterEach(async () => {
  await setLocale('en-US')
})

describe('dynamic i18n key families', () => {
  it('matches the actual option arrays and has every key in en-US', () => {
    const actual = {
      'ExpenseForm.Expense.recurrenceRule.': RECURRENCES.map((item) =>
        item.value.toLowerCase(),
      ),
      'Expenses.Groups.': [...DATE_GROUP_KEYS],
      'Theme.': [...THEME_OPTIONS],
      'GroupTabs.': GROUP_TABS.map((tab) => tab.key),
      'Stats.range.': STATS_RANGES.map((range) => range.value),
    }

    expect(actual).toEqual(dynamicFamilies)

    for (const [prefix, suffixes] of Object.entries(dynamicFamilies)) {
      for (const suffix of suffixes) {
        expect(enKeys, `${prefix}${suffix}`).toContain(`${prefix}${suffix}`)
      }
    }
  })
})

describe('locale quality', () => {
  it('uses the theme, action and sync meanings in the main locales', async () => {
    for (const [locale, expected] of Object.entries(EXPECTED_ACTIONS)) {
      await setLocale(locale)
      for (const [key, value] of Object.entries(expected)) {
        expect(i18n.t(key), `${locale} ${key}`).toBe(value)
      }
    }
  })

  it('has no empty message strings in any catalogue', () => {
    for (const [path, catalogue] of Object.entries(catalogues)) {
      for (const [key, value] of Object.entries(flatten(catalogue))) {
        if (typeof value === 'string') {
          expect(value.trim(), `${path} ${key}`).not.toBe('')
        }
      }
    }
  })
})
