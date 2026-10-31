/**
 * Recurrence date arithmetic.
 *
 * Pure JavaScript mirror of `backend/app/utils/recurrence.py`. Monthly
 * recurrence clamps to the last valid day of the next month and keeps that day
 * for later frames (Jan 31 → Feb 28 → Mar 28).
 */

export const RECURRENCE_RULES = ['NONE', 'DAILY', 'WEEKLY', 'MONTHLY']

/**
 * @param {string|null|undefined} rule
 * @param {Date|string} prior
 * @returns {Date}
 */
export function calculateNextDate(rule, prior) {
  const value = prior instanceof Date ? new Date(prior.getTime()) : new Date(prior)
  if (Number.isNaN(value.getTime())) return value
  const normalized = String(rule || 'NONE').toUpperCase()

  if (normalized === 'DAILY') {
    value.setUTCDate(value.getUTCDate() + 1)
    return value
  }
  if (normalized === 'WEEKLY') {
    value.setUTCDate(value.getUTCDate() + 7)
    return value
  }
  if (normalized !== 'MONTHLY') return value

  let nextMonth = value.getUTCMonth() + 1
  let nextYear = value.getUTCFullYear()
  if (nextMonth > 11) {
    nextMonth = 0
    nextYear += 1
  }
  const lastDay = new Date(Date.UTC(nextYear, nextMonth + 1, 0)).getUTCDate()
  const day = Math.min(value.getUTCDate(), lastDay)
  return new Date(
    Date.UTC(
      nextYear,
      nextMonth,
      day,
      value.getUTCHours(),
      value.getUTCMinutes(),
      value.getUTCSeconds(),
      value.getUTCMilliseconds(),
    ),
  )
}
