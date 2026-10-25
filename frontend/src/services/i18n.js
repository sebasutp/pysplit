/**
 * i18next configuration.
 *
 * Locale files are ported from the reference application and completed from
 * en-US so every locale has the same key set. The selected locale is stored in
 * localStorage and mirrored to the reference NEXT_LOCALE cookie for parity
 * with the old application.
 */

import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

const modules = import.meta.glob('../locales/messages/*.json', {
  eager: true,
  import: 'default',
})

/** @type {Record<string, Record<string, unknown>>} */
const resources = {}
for (const [path, messages] of Object.entries(modules)) {
  const match = /\/([^/]+)\.json$/.exec(path)
  if (!match) continue
  resources[match[1]] = /** @type {Record<string, unknown>} */ (messages)
}

export const SUPPORTED_LOCALES = Object.keys(resources).sort((left, right) => {
  if (left === 'en-US') return -1
  if (right === 'en-US') return 1
  return left.localeCompare(right)
})

const STORAGE_KEY = 'pysplit-locale'
const COOKIE_NAME = 'NEXT_LOCALE'
const DEFAULT_LOCALE = 'en-US'

/** @param {string} name @returns {string | null} */
function readCookie(name) {
  if (typeof document === 'undefined' || !document.cookie) return null
  for (const part of document.cookie.split(';')) {
    const separator = part.indexOf('=')
    if (separator < 0) continue
    if (part.slice(0, separator).trim() === name) {
      return decodeURIComponent(part.slice(separator + 1).trim())
    }
  }
  return null
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
  await i18n.changeLanguage(resolved)
  if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, resolved)
  if (typeof document !== 'undefined') {
    document.cookie = `${COOKIE_NAME}=${encodeURIComponent(resolved)}; Path=/; SameSite=Lax`
  }
  applyDocumentLocale(resolved)
  return resolved
}

if (!i18n.isInitialized) {
  await i18n.use(initReactI18next).init({
    resources: /** @type {any} */ (resources),
    lng: initialLocale(),
    fallbackLng: DEFAULT_LOCALE,
    supportedLngs: SUPPORTED_LOCALES,
    interpolation: { escapeValue: false },
    react: { useSuspense: false },
    returnNull: false,
  })
  applyDocumentLocale(getLocale())
}

export default i18n
