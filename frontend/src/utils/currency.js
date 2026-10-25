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
