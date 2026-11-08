/**
 * Currency formatting helpers.
 *
 * Money crossing the API is always integer minor units.
 */

import { decimalDigits } from './domain/currency'

/**
 * @typedef {Object} Currency
 * @property {string} code ISO-4217 code, empty for a custom symbol
 * @property {string} symbol Display symbol
 */

/**
 * @param {{currency?: string|null, currency_code?: string|null}} group
 * @returns {Currency}
 */
export function getCurrencyFromGroup(group) {
  return {
    code: group.currency_code || '',
    symbol: group.currency || '',
  }
}

/** Common ISO-4217 currencies offered by the expense and group forms. */
export const COMMON_CURRENCIES = /** @type {{code: string, name: string}[]} */ ([
  { code: 'USD', name: 'US Dollar' },
  { code: 'EUR', name: 'Euro' },
  { code: 'GBP', name: 'British Pound' },
  { code: 'CAD', name: 'Canadian Dollar' },
  { code: 'AUD', name: 'Australian Dollar' },
  { code: 'JPY', name: 'Japanese Yen' },
  { code: 'CNY', name: 'Chinese Yuan' },
  { code: 'CHF', name: 'Swiss Franc' },
  { code: 'INR', name: 'Indian Rupee' },
  { code: 'BRL', name: 'Brazilian Real' },
  { code: 'MXN', name: 'Mexican Peso' },
  { code: 'SEK', name: 'Swedish Krona' },
  { code: 'NOK', name: 'Norwegian Krone' },
  { code: 'DKK', name: 'Danish Krone' },
  { code: 'PLN', name: 'Polish Zloty' },
  { code: 'CZK', name: 'Czech Koruna' },
  { code: 'TRY', name: 'Turkish Lira' },
  { code: 'ZAR', name: 'South African Rand' },
])

/** @type {Record<string, string>} */
export const CURRENCY_SYMBOLS = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  CAD: 'CA$',
  AUD: 'A$',
  JPY: '¥',
  CNY: '¥',
  CHF: 'CHF',
  INR: '₹',
  BRL: 'R$',
  MXN: 'MX$',
  SEK: 'kr',
  NOK: 'kr',
  DKK: 'kr',
  PLN: 'zł',
  CZK: 'Kč',
  TRY: '₺',
  ZAR: 'R',
}

/**
 * @param {string} code
 * @returns {string}
 */
export function currencyLabel(code) {
  const normalized = code.toUpperCase()
  const match = COMMON_CURRENCIES.find((item) => item.code === normalized)
  if (match) return `${match.name} (${match.code})`
  try {
    const names = new Intl.DisplayNames(undefined, { type: 'currency' })
    const name = names.of(normalized)
    if (name && name !== normalized) return `${name} (${normalized})`
  } catch {
    // Not an ISO-4217 code; fall back to the raw value.
  }
  return normalized
}

/**
 * @param {string} text
 * @param {string} character
 * @returns {number}
 */
function count(text, character) {
  return text.split(character).length - 1
}

/**
 * Resolve the decimal and grouping separators used by a locale.
 *
 * @param {string} locale
 * @returns {{decimal: string, group: string}|null}
 */
function localeSeparators(locale) {
  try {
    const parts = new Intl.NumberFormat(locale).formatToParts(1234567.89)
    let decimal = ''
    let group = ''
    for (const part of parts) {
      if (part.type === 'decimal') decimal = part.value
      else if (part.type === 'group') group = part.value
    }
    return decimal ? { decimal, group } : null
  } catch {
    return null
  }
}

/**
 * Normalize separators when the locale is unknown.
 *
 * A single `.` or `,` is treated as a decimal separator (the historical
 * behaviour). When both appear, the right-most one is the decimal separator.
 * Repeated separators that split the text into groups of three are grouping.
 *
 * @param {string} text
 * @returns {string}
 */
function normalizeGeneric(text) {
  const dots = count(text, '.')
  const commas = count(text, ',')
  if (dots && commas) {
    const decimal = text.lastIndexOf('.') > text.lastIndexOf(',') ? '.' : ','
    const group = decimal === '.' ? ',' : '.'
    const parts = text.split(decimal)
    const whole = parts.slice(0, -1).join('').split(group).join('')
    return `${whole}.${parts[parts.length - 1]}`
  }
  const separator = dots ? '.' : commas ? ',' : ''
  if (!separator) return text
  const parts = text.split(separator)
  if (parts.length > 2) {
    const grouped =
      parts.slice(1).every((part) => part.length === 3) && parts[0].length <= 3
    if (grouped) return parts.join('')
  }
  return `${parts.slice(0, -1).join('')}.${parts[parts.length - 1]}`
}

/**
 * Normalize a locale-aware amount string to a plain `1234.56` number string.
 *
 * @param {string} text
 * @param {string} [locale]
 * @returns {string}
 */
function normalizeNumber(text, locale) {
  if (locale) {
    const separators = localeSeparators(locale)
    if (separators) {
      const { decimal, group } = separators
      const hasDecimal = Boolean(decimal) && text.includes(decimal)
      const hasGroup = Boolean(group) && text.includes(group)
      if (hasDecimal && (!hasGroup || text.lastIndexOf(decimal) > text.lastIndexOf(group))) {
        const last = text.lastIndexOf(decimal)
        const stripGroup = (/** @type {string} */ part) =>
          group ? part.split(group).join('') : part
        const whole = stripGroup(text.slice(0, last)).split(decimal).join('')
        const fraction = stripGroup(text.slice(last + 1))
        return `${whole}.${fraction}`
      }
      if (!hasDecimal && hasGroup) {
        const parts = text.split(group)
        const grouped =
          parts.length > 1 &&
          parts[0].length <= 3 &&
          parts.slice(1).every((part) => part.length === 3)
        if (grouped) return parts.join('')
        // The group character is being used as a decimal separator.
        const last = text.lastIndexOf(group)
        return `${text.slice(0, last).split(group).join('')}.${text.slice(last + 1)}`
      }
    }
  }
  return normalizeGeneric(text)
}

/**
 * Parse a human-entered amount ("12.34", "1 234,56") into minor units.
 *
 * When a currency is supplied its number of decimal digits is respected, so
 * zero-decimal currencies such as JPY round to whole units. A locale makes
 * grouping and decimal separators unambiguous; without one, both separators
 * are inferred from their position (see `normalizeGeneric`).
 *
 * @param {string|number} value
 * @param {string} [currencyCode]
 * @param {string} [locale]
 * @returns {number}
 */
export function parseAmount(value, currencyCode, locale) {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 0
    return Math.round(value * 10 ** decimalDigits(currencyCode))
  }

  let text = String(value ?? '').trim()
  if (!text) return 0

  let negative = false
  if (/^[+−-]/.test(text)) {
    negative = text[0] === '-' || text[0] === '−'
    text = text.slice(1)
  }
  text = text.replace(/\s/g, '')
  if (!text || text === '.' || text === ',') return 0

  const normalized = normalizeNumber(text, locale)
  const parsed = Number(normalized)
  if (!Number.isFinite(parsed)) return 0

  const minor = Math.round(parsed * 10 ** decimalDigits(currencyCode))
  return negative ? -minor : minor
}

/**
 * Format minor units as a plain major-unit input value (no currency symbol).
 *
 * @param {number|null|undefined} amount
 * @param {string} [currencyCode]
 * @returns {string}
 */
export function majorUnits(amount, currencyCode) {
  if (amount === null || amount === undefined) return ''
  const digits = decimalDigits(currencyCode)
  const value = Number(amount) / 10 ** digits
  if (!Number.isFinite(value)) return ''
  let text = value.toFixed(digits)
  if (text.includes('.')) text = text.replace(/0+$/, '').replace(/\.$/, '')
  if (text === '' || text === '-0') return '0'
  return text
}

/**
 * @param {Currency} currency
 * @param {number} amount Minor units
 * @param {string} [locale]
 * @returns {string}
 */
export function formatCurrency(currency, amount, locale = 'en-US') {
  const digits = decimalDigits(currency.code)
  if (currency.code) {
    try {
      const formatter = new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: currency.code,
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })
      return formatter.format(amount / 10 ** digits)
    } catch {
      // Fall through to the symbol form for unknown/invalid codes.
    }
  }
  const sign = amount < 0 ? '-' : ''
  const absolute = Math.abs(amount)
  if (digits === 0) {
    return `${sign}${currency.symbol}${absolute.toLocaleString(locale, {
      maximumFractionDigits: 0,
    })}`
  }
  const factor = 10 ** digits
  const whole = Math.floor(absolute / factor)
  const fraction = String(absolute % factor).padStart(digits, '0')
  return `${sign}${currency.symbol}${whole.toLocaleString(locale)}.${fraction}`
}
