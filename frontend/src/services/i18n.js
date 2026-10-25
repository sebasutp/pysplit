/**
 * i18next configuration.
 *
 * Locale files are ported from the reference application and completed from
 * en-US so every locale has the same key set. Only en-US is bundled into the
 * entry chunk (it is also the fallback); the active locale is imported on
 * demand and registered with i18next, so the other 34 catalogues stay out of
 * the initial download. The selected locale is stored in localStorage and
 * mirrored to the reference NEXT_LOCALE cookie for parity with the old
 * application.
 */

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import enUS from '../locales/messages/en-US.json'
import { readCookie } from './cookies'

const LOCALE_DIR = '../locales/messages/'
const DEFAULT_LOCALE = 'en-US'
const STORAGE_KEY = 'pysplit-locale'
const COOKIE_NAME = 'NEXT_LOCALE'

/**
 * The ported catalogues use the reference application's single-brace
 * placeholders (`{name}`), while i18next interpolates `{{name}}`. Match a
 * single-brace placeholder without also matching half of a double-brace one.
 */
const SINGLE_BRACE_PLACEHOLDER = /(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})/g

/**
 * Rewrite single-brace placeholders to i18next syntax throughout a catalogue.
 * Non-string leaves are returned unchanged; existing `{{name}}` sequences are
 * left alone.
 *
 * @param {unknown} value
 * @returns {any}
 */
export function normalizeMessages(value) {
  if (typeof value === 'string') {
    return value.replace(SINGLE_BRACE_PLACEHOLDER, '{{$1}}')
  }
  if (Array.isArray(value)) return value.map(normalizeMessages)
  if (value && typeof value === 'object') {
    /** @type {Record<string, unknown>} */
    const result = {}
    for (const [key, child] of Object.entries(value)) {
      result[key] = normalizeMessages(child)
    }
    return result
  }
  return value
}

/**
 * Lazy loaders for every catalogue except the eagerly bundled fallback.
 *
 * @type {Record<string, () => Promise<Record<string, unknown>>>}
 */
const localeLoaders = /** @type {any} */ (
  import.meta.glob(['../locales/messages/*.json', '!../locales/messages/en-US.json'], {
    import: 'default',
  })
)

export const SUPPORTED_LOCALES = [
  DEFAULT_LOCALE,
  ...Object.keys(localeLoaders).map((path) => path.slice(LOCALE_DIR.length, -'.json'.length)),
].sort((left, right) => {
  if (left === DEFAULT_LOCALE) return -1
  if (right === DEFAULT_LOCALE) return 1
  return left.localeCompare(right)
})

/**
 * Fetch one catalogue. Returns null when the locale has no file.
 *
 * @param {string} locale
 * @returns {Promise<Record<string, unknown> | null>}
 */
async function loadLocaleMessages(locale) {
  const loader = localeLoaders[`${LOCALE_DIR}${locale}.json`]
  if (!loader) return null
  return normalizeMessages(await loader())
}

/**
 * Make sure i18next holds the catalogue for `locale` before it becomes active,
 * so a language switch never renders raw keys for a frame.
 *
 * @param {string} locale
 * @returns {Promise<void>}
 */
async function ensureLocaleBundle(locale) {
  if (i18n.hasResourceBundle(locale, 'translation')) return
  const messages = await loadLocaleMessages(locale)
  if (messages) i18n.addResourceBundle(locale, 'translation', messages, true, true)
}

/**
 * Match a browser language tag to one of the ported locale files.
 *
 * @param {string | null | undefined} candidate
 * @returns {string | null}
 */
export function matchLocale(candidate) {
  if (!candidate) return null
  const normalised = candidate.replace('_', '-').toLowerCase()
  const exact = SUPPORTED_LOCALES.find((locale) => locale.toLowerCase() === normalised)
  if (exact) return exact
  const prefix = normalised.split('-')[0]
  return (
    SUPPORTED_LOCALES.find((locale) => locale.toLowerCase() === prefix) ||
    SUPPORTED_LOCALES.find((locale) => locale.toLowerCase().startsWith(`${prefix}-`)) ||
    null
  )
}

function initialLocale() {
  const stored = typeof localStorage === 'undefined' ? null : localStorage.getItem(STORAGE_KEY)
  const cookie = readCookie(COOKIE_NAME)
  const browser =
    typeof navigator === 'undefined' ? null : navigator.languages?.[0] || navigator.language
  return matchLocale(stored) || matchLocale(cookie) || matchLocale(browser) || DEFAULT_LOCALE
}

/** @param {string} locale */
export function localeLabel(locale) {
  const base = locale.split('-')[0]
  try {
    const names = new Intl.DisplayNames([locale], { type: 'language' })
    return names.of(base) || locale
  } catch {
    return locale
  }
}

/** @param {string} locale */
export function applyDocumentLocale(locale) {
  if (typeof document === 'undefined') return
  document.documentElement.lang = locale
  document.documentElement.dir = ['ar', 'he', 'fa'].includes(locale.split('-')[0]) ? 'rtl' : 'ltr'
}

export function getLocale() {
  return i18n.resolvedLanguage || i18n.language || DEFAULT_LOCALE
}

/**
 * @param {string} locale
 * @returns {Promise<string>}
 */
export async function setLocale(locale) {
  const resolved = matchLocale(locale) || DEFAULT_LOCALE
  try {
    await ensureLocaleBundle(resolved)
  } catch {
    // A failed chunk fetch should not block switching back to a bundled
    // locale; missing keys fall back to the en-US resources.
  }
  await i18n.changeLanguage(resolved)
  if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, resolved)
  if (typeof document !== 'undefined') {
    document.cookie = `${COOKIE_NAME}=${encodeURIComponent(resolved)}; Path=/; SameSite=Lax`
  }
  applyDocumentLocale(resolved)
  return resolved
}

// Await the initial catalogue (and i18next init) at module scope: App imports
// this module before rendering, so the first paint already has translations.
const enUSMessages = normalizeMessages(enUS)
const startLocale = initialLocale()
const startMessages =
  startLocale === DEFAULT_LOCALE
    ? enUSMessages
    : await loadLocaleMessages(startLocale).catch(() => null)

if (!i18n.isInitialized) {
  await i18n.use(initReactI18next).init({
    resources: {
      [DEFAULT_LOCALE]: { translation: enUSMessages },
      ...(startMessages ? { [startLocale]: { translation: startMessages } } : {}),
    },
    lng: startLocale,
    fallbackLng: DEFAULT_LOCALE,
    supportedLngs: SUPPORTED_LOCALES,
    ns: ['translation'],
    defaultNS: 'translation',
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
    returnNull: false,
  })
  applyDocumentLocale(getLocale())
}

export default i18n
