/**
 * Currency metadata and minor-unit formatting.
 *
 * Pure JavaScript mirror of `backend/app/utils/currency.py`.
 */

export const ZERO_DECIMAL_CURRENCIES = new Set([
  'JPY',
  'HUF',
  'ISK',
  'IDR',
  'KRW',
  'VND',
  'COP',
])

/**
 * @param {string|null|undefined} currencyCode
 * @returns {number}
 */
export function decimalDigits(currencyCode) {
  if (currencyCode && ZERO_DECIMAL_CURRENCIES.has(String(currencyCode).toUpperCase())) {
    return 0
  }
  return 2
}

/**
 * @param {string|null|undefined} currencyCode
 * @param {string} fallback
 * @returns {string}
 */
export function currencyLabelForExport(currencyCode, fallback) {
  return currencyCode || fallback
}

/**
 * @param {number} amount
 * @param {string|null|undefined} currencyCode
 * @returns {string}
 */
export function formatAmountAsDecimal(amount, currencyCode) {
  const digits = decimalDigits(currencyCode)
  return (Number(amount) / 10 ** digits).toFixed(digits)
}

/**
 * Format the way JSON2CSV renders a JavaScript number: trailing zeros dropped.
 *
 * @param {number} amount
 * @param {string|null|undefined} currencyCode
 * @returns {string}
 */
export function formatAmountForCsv(amount, currencyCode) {
  const digits = decimalDigits(currencyCode)
  let text = (Number(amount) / 10 ** digits).toFixed(digits)
  if (text.includes('.')) text = text.replace(/0+$/, '').replace(/\.$/, '')
  if (text === '' || text === '-0') return '0'
  return text
}
