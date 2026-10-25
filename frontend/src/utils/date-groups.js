/**
 * Group expenses into the reference date buckets.
 *
 * The API exposes `expense_date` as YYYY-MM-DD, so grouping uses the UTC date
 * and never shifts with the viewer's timezone.
 */

/** @typedef {{key: string, label: string, expenses: any[]}} ExpenseDateGroup */

/** @param {Date} date @returns {string} */
function isoDate(date) {
  return date.toISOString().slice(0, 10)
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
    const monthLong = formatter(locale, { month: 'long' })
    const monthShort = formatter(locale, { month: 'short' })
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
    // Attach a formatted date label for the row itself.
    expense._groupLabel =
      value === today
        ? 'Today'
        : `${monthShort.format(date)} ${date.getUTCDate()}, ${date.getUTCFullYear()}`
    void monthLong
    group.expenses.push(expense)
  }

  return [...groups.values()]
}
