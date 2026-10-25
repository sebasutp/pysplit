/**
 * Currency formatting helpers.
 *
 * Money crossing the API is always integer minor units.
 */

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
  const match = COMMON_CURRENCIES.find((item) => item.code === code.toUpperCase())
  return match ? `${match.name} (${match.code})` : code.toUpperCase()
}

/**
 * Parse a human-entered amount ("12.34", "1 234,56") into minor units.
 *
 * @param {string|number} value
 * @returns {number}
 */
export function parseAmount(value) {
  const normalized = String(value ?? '')
    .replace(/\s/g, '')
    .replace(',', '.')
  if (!normalized || normalized === '-' || normalized === '.') return 0
  const parsed = Number(normalized)
  if (!Number.isFinite(parsed)) return 0
  return Math.round(parsed * 100)
}

/**
 * Format minor units as a plain major-unit input value (no currency symbol).
 *
 * @param {number|null|undefined} amount
 * @returns {string}
 */
export function majorUnits(amount) {
  if (amount === null || amount === undefined) return ''
  return (amount / 100).toFixed(2).replace(/\.00$/, '')
}

/**
 * @param {Currency} currency
 * @param {number} amount Minor units
 * @param {string} [locale]
 * @returns {string}
 */
export function formatCurrency(currency, amount, locale = 'en-US') {
  if (currency.code) {
    try {
      const formatter = new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: currency.code,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
      return formatter.format(amount / 100)
    } catch {
      // Fall through to the symbol form for unknown/invalid codes.
    }
  }
  const sign = amount < 0 ? '-' : ''
  const absolute = Math.abs(amount)
  const whole = Math.floor(absolute / 100)
  const cents = String(absolute % 100).padStart(2, '0')
  return `${sign}${currency.symbol}${whole.toLocaleString(locale)}.${cents}`
}
