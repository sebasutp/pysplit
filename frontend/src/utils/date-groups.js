/**
 * Group expenses into the reference date buckets.
 *
 * The API exposes `expense_date` as YYYY-MM-DD, so grouping uses the UTC date
 * and never shifts with the viewer's timezone.
 */

/** @typedef {{key: string, label: string, expenses: any[]}} ExpenseDateGroup */

/** Keys produced by `groupExpensesByDate`; mirrors the `Expenses.Groups.*` messages. */
export const DATE_GROUP_KEYS = /** @type {const} */ ([
  'today',
  'week',
  'month',
  'lastMonth',
  'year',
  'lastYear',
  'older',
])

/** @param {Date} date @returns {string} */
function isoDate(date) {
  return date.toISOString().slice(0, 10)
}

/**
 * Format a date-only API value (`YYYY-MM-DD`) in the viewer's locale. Parsing
 * at UTC midnight keeps the displayed day stable across timezones.
 *
 * @param {string|null|undefined} value
 * @param {string} [locale]
 * @returns {string}
 */
export function formatExpenseDate(value, locale = 'en-US') {
  const text = String(value || '').slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return value ? String(value) : ''
  const date = new Date(`${text}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return text
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeZone: 'UTC',
  }).format(date)
}

/**
 * @param {string|string[]} locales
 * @param {{month: 'long'|'short', year?: 'numeric'}} options
 * @returns {Intl.DateTimeFormat}
 */
function formatter(locales, options) {
  return new Intl.DateTimeFormat(locales, { timeZone: 'UTC', ...options })
}

/**
 * @param {any[]} expenses
 * @param {string} [locale]
 * @returns {ExpenseDateGroup[]}
 */
export function groupExpensesByDate(expenses, locale = 'en-US') {
  const now = new Date()
  const today = isoDate(now)
  const startOfWeek = new Date(now)
  startOfWeek.setUTCDate(now.getUTCDate() - ((now.getUTCDay() + 6) % 7))
  const startOfMonth = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))
  const startOfLastMonth = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1))
  const startOfYear = new Date(Date.UTC(now.getUTCFullYear(), 0, 1))
  const startOfLastYear = new Date(Date.UTC(now.getUTCFullYear() - 1, 0, 1))
  // Build the formatter once instead of once per expense.
  const monthShort = formatter(locale, { month: 'short' })

  /** @type {Map<string, ExpenseDateGroup>} */
  const groups = new Map()
  /** @param {string} key @param {string} label @returns {ExpenseDateGroup} */
  function add(key, label) {
    const existing = groups.get(key)
    if (existing) return existing
    const created = { key, label, expenses: [] }
    groups.set(key, created)
    return created
  }

  for (const expense of expenses) {
    const value = String(expense.expense_date || '').slice(0, 10)
    const date = new Date(`${value}T00:00:00Z`)
    let group
    if (value === today) {
      group = add('today', 'Today')
    } else if (value > isoDate(startOfWeek)) {
      group = add('week', 'Earlier this week')
    } else if (value >= isoDate(startOfMonth)) {
      group = add('month', 'Earlier this month')
    } else if (value >= isoDate(startOfLastMonth)) {
      group = add('lastMonth', 'Last month')
    } else if (value >= isoDate(startOfYear)) {
      group = add('year', 'Earlier this year')
    } else if (value >= isoDate(startOfLastYear)) {
      group = add('lastYear', 'Last year')
    } else {
      group = add('older', 'Older')
    }
    // Copy the API object so the row label never mutates server data.
    group.expenses.push({
      ...expense,
      _groupLabel:
        value === today
          ? 'Today'
          : `${monthShort.format(date)} ${date.getUTCDate()}, ${date.getUTCFullYear()}`,
    })
  }

  return [...groups.values()]
}
