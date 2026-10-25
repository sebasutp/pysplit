/** Statistics period presets, mirroring the reference stats-range helper. */

export const STATS_RANGES = /** @type {const} */ ([
  { value: 'all', label: 'All time' },
  { value: 'thisMonth', label: 'This month' },
  { value: 'last30', label: 'Last 30 days' },
  { value: 'thisYear', label: 'This year' },
  { value: 'custom', label: 'Custom range' },
])

/** @param {Date} date @returns {string} */
function iso(date) {
  return date.toISOString().slice(0, 10)
}

/**
 * @param {string} preset
 * @param {{from?: string, to?: string}} [custom]
 * @returns {{from: string|null, to: string|null}}
 */
export function resolveRange(preset, custom = {}) {
  const now = new Date()
  if (preset === 'thisMonth') {
    return {
      from: iso(new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))),
      to: iso(now),
    }
  }
  if (preset === 'last30') {
    const start = new Date(now)
    start.setUTCDate(start.getUTCDate() - 29)
    return { from: iso(start), to: iso(now) }
  }
  if (preset === 'thisYear') {
    return { from: `${now.getUTCFullYear()}-01-01`, to: iso(now) }
  }
  if (preset === 'custom') {
    return { from: custom.from || null, to: custom.to || null }
  }
  return { from: null, to: null }
}

/**
 * "Mar 2020" for a YYYY-MM API month.
 *
 * @param {string} month
 * @param {string} [locale]
 * @returns {string}
 */
export function monthLabel(month, locale = 'en-US') {
  const [year, monthNumber] = month.split('-').map(Number)
  if (!year || !monthNumber) return month
  return new Intl.DateTimeFormat(locale, {
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, monthNumber - 1, 1)))
}
