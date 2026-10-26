/**
 * Spending statistics and totals.
 *
 * Pure JavaScript mirror of `backend/app/utils/totals.py`. Reimbursements are
 * excluded from spending statistics but included in balances, as in the
 * reference application.
 */

import { getExpenseShares, getParticipantShare } from './shares'

export const RECURRENCE_PERIODS = ['DAILY', 'WEEKLY', 'MONTHLY']

const PERIOD_FACTORS = {
  DAILY: { perMonth: 365.25 / 12, perYear: 365.25 },
  WEEKLY: { perMonth: 365.25 / 12 / 7, perYear: 365.25 / 7 },
  MONTHLY: { perMonth: 1, perYear: 12 },
}

/**
 * JavaScript `Math.round` semantics are not the same for negative halves as
 * Python's floor(x + 0.5); statistics fixtures depend on the latter.
 *
 * @param {number} value
 * @returns {number}
 */
export function jsRound(value) {
  return Math.floor(value + 0.5)
}

/**
 * @param {any} expense
 * @returns {string}
 */
export function expenseDateString(expense) {
  const value = expense?.expense_date ?? expense?.expenseDate
  if (value instanceof Date) return value.toISOString().slice(0, 10)
  return String(value).slice(0, 10)
}

/**
 * @param {any} expense
 * @returns {string}
 */
function paidById(expense) {
  let value = expense?.paid_by_id
  if (value == null && expense?.paidBy && typeof expense.paidBy === 'object') {
    value = expense.paidBy.id
  }
  return String(value)
}

/**
 * @param {any} expense
 * @returns {any}
 */
function category(expense) {
  return expense?.category && typeof expense.category === 'object' ? expense.category : {}
}

/**
 * @param {any} expense
 * @returns {any[]}
 */
function paidFor(expense) {
  const raw = expense?.paid_for ?? expense?.paidFor ?? []
  const rows = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    let participant = item.participant_id
    if (participant == null && item.participant && typeof item.participant === 'object') {
      participant = item.participant.id
    }
    if (participant == null) continue
    rows.push({
      participant: { id: String(participant) },
      participant_id: String(participant),
      shares: Number(item.shares ?? 1),
    })
  }
  return rows
}

/**
 * @param {any} expense
 * @returns {any}
 */
function shareInput(expense) {
  return {
    id: expense?.id,
    amount: Number(expense?.amount ?? 0),
    split_mode: expense?.split_mode ?? expense?.splitMode ?? 'EVENLY',
    paid_for: paidFor(expense),
    expense_date: expense?.expense_date ?? expense?.expenseDate,
  }
}

/**
 * @param {any[]} expenses
 * @param {string|null} [dateFrom]
 * @param {string|null} [dateTo]
 * @returns {any[]}
 */
export function filterExpensesByDateRange(expenses, dateFrom = null, dateTo = null) {
  if (!dateFrom && !dateTo) return [...expenses]
  return expenses.filter((expense) => {
    const value = expenseDateString(expense)
    if (dateFrom && value < dateFrom) return false
    if (dateTo && value > dateTo) return false
    return true
  })
}

/**
 * @param {any[]} expenses
 * @returns {number}
 */
export function getTotalGroupSpending(expenses) {
  return expenses
    .filter((expense) => !expense?.is_reimbursement)
    .reduce((sum, expense) => sum + Number(expense.amount), 0)
}

/**
 * @param {string|null} activeUserId
 * @param {any[]} expenses
 * @returns {number}
 */
export function getTotalActiveUserPaidFor(activeUserId, expenses) {
  return expenses
    .filter((expense) => paidById(expense) === activeUserId && !expense?.is_reimbursement)
    .reduce((sum, expense) => sum + Number(expense.amount), 0)
}

/**
 * @param {string|null} participantIdValue
 * @param {any} expense
 * @returns {number}
 */
export function calculateShare(participantIdValue, expense) {
  if (expense?.is_reimbursement) return 0
  return getParticipantShare(participantIdValue, shareInput(expense))
}

/**
 * @param {string|null} activeUserId
 * @param {any[]} expenses
 * @returns {number}
 */
export function getTotalActiveUserShare(activeUserId, expenses) {
  return expenses.reduce((sum, expense) => sum + calculateShare(activeUserId, expense), 0)
}

/**
 * @param {any[]} expenses
 * @returns {{categoryId: number, grouping: string, name: string, total: number}[]}
 */
export function getSpendingByCategory(expenses) {
  /** @type {Map<number, {categoryId: number, grouping: string, name: string, total: number}>} */
  const totals = new Map()
  for (const expense of expenses) {
    if (expense?.is_reimbursement) continue
    const value = category(expense)
    const categoryId = Number(value.id ?? expense?.category_id ?? 0) || 0
    const amount = Number(expense.amount)
    const existing = totals.get(categoryId)
    if (existing) {
      existing.total += amount
    } else {
      totals.set(categoryId, {
        categoryId,
        grouping: value.grouping || 'Uncategorized',
        name: value.name || 'General',
        total: amount,
      })
    }
  }
  return [...totals.values()]
    .filter((row) => Number(row.total) !== 0)
    .sort((first, second) => Number(second.total) - Number(first.total))
}

/**
 * @param {any} expense
 * @returns {string}
 */
function dateKey(expense) {
  return String(expense?.expense_date ?? expense?.expenseDate ?? '')
}

/**
 * @param {any[]} expenses
 * @param {number} categoryId
 * @returns {any[]}
 */
export function getExpensesByCategory(expenses, categoryId) {
  return expenses
    .filter(
      (expense) =>
        !expense?.is_reimbursement &&
        Number(category(expense).id ?? expense?.category_id ?? 0) === Number(categoryId),
    )
    .sort((first, second) => (dateKey(first) < dateKey(second) ? 1 : -1))
}

/**
 * @param {any[]} expenses
 * @param {string} month
 * @returns {any[]}
 */
export function getExpensesByMonth(expenses, month) {
  return expenses
    .filter(
      (expense) =>
        !expense?.is_reimbursement && expenseDateString(expense).slice(0, 7) === month,
    )
    .sort((first, second) => (dateKey(first) < dateKey(second) ? 1 : -1))
}

/**
 * @param {{id: string, name: string}[]} participants
 * @param {any[]} expenses
 * @returns {{participantId: string, name: string, paid: number, paidCount: number, share: number}[]}
 */
export function getSpendingByParticipant(participants, expenses) {
  /** @type {Map<string, {paid: number, paidCount: number, share: number}>} */
  const totals = new Map(
    participants.map((participant) => [
      String(participant.id),
      { paid: 0, paidCount: 0, share: 0 },
    ]),
  )

  for (const expense of expenses) {
    if (expense?.is_reimbursement) continue
    const payer = totals.get(paidById(expense))
    if (payer) {
      payer.paid += Number(expense.amount)
      payer.paidCount += 1
    }
    for (const [participantIdValue, share] of getExpenseShares(shareInput(expense))) {
      const entry = totals.get(participantIdValue)
      if (entry) entry.share += share
    }
  }

  return participants
    .map((participant) => {
      const values = totals.get(String(participant.id)) ?? {
        paid: 0,
        paidCount: 0,
        share: 0,
      }
      return {
        participantId: String(participant.id),
        name: String(participant.name ?? ''),
        paid: values.paid,
        paidCount: values.paidCount,
        share: values.share,
      }
    })
    .sort((first, second) => Number(second.paid) - Number(first.paid))
}

/**
 * @param {any[]} expenses
 * @returns {{month: string, total: number}[]}
 */
export function getSpendingOverTime(expenses) {
  /** @type {Map<string, number>} */
  const totals = new Map()
  for (const expense of expenses) {
    if (expense?.is_reimbursement) continue
    const month = expenseDateString(expense).slice(0, 7)
    totals.set(month, (totals.get(month) ?? 0) + Number(expense.amount))
  }
  if (!totals.size) return []

  const months = [...totals.keys()].sort()
  const [firstYear, firstMonth] = months[0].split('-').map(Number)
  const [lastYear, lastMonth] = months[months.length - 1].split('-').map(Number)

  const result = []
  let year = firstYear
  let month = firstMonth
  while (year < lastYear || (year === lastYear && month <= lastMonth)) {
    const key = `${year}-${String(month).padStart(2, '0')}`
    result.push({ month: key, total: totals.get(key) ?? 0 })
    month += 1
    if (month > 12) {
      month = 1
      year += 1
    }
  }
  return result
}

/**
 * @param {any[]} expenses
 * @returns {any}
 */
export function getSpendingSummary(expenses) {
  const relevant = expenses.filter((expense) => !expense?.is_reimbursement)
  const expenseCount = relevant.length
  const totalSpending = relevant.reduce((sum, expense) => sum + Number(expense.amount), 0)

  let largest = null
  for (const expense of relevant) {
    if (!largest || Number(expense.amount) > Number(largest.amount)) {
      largest = { title: String(expense.title ?? ''), amount: Number(expense.amount) }
    }
  }
  const dates = relevant.map(expenseDateString).sort()
  return {
    expenseCount,
    totalSpending,
    averageExpense: expenseCount ? jsRound(totalSpending / expenseCount) : 0,
    largestExpense: largest,
    firstDate: dates[0] ?? null,
    lastDate: dates[dates.length - 1] ?? null,
  }
}

/**
 * @param {any[]} expenses
 * @returns {any}
 */
export function getRecurringSpending(expenses) {
  const byPeriod = RECURRENCE_PERIODS.map((period) => {
    const matching = expenses.filter(
      (expense) =>
        !expense?.is_reimbursement &&
        (expense?.recurrence_rule ?? expense?.recurrenceRule) === period,
    )
    return {
      period,
      count: matching.length,
      total: matching.reduce((sum, expense) => sum + Number(expense.amount), 0),
    }
  })

  /** @param {'perMonth'|'perYear'} factor */
  const estimate = (factor) =>
    jsRound(
      byPeriod.reduce((sum, row) => sum + row.total * PERIOD_FACTORS[/** @type {keyof typeof PERIOD_FACTORS} */ (row.period)][factor], 0),
    )

  return {
    count: byPeriod.reduce((sum, row) => sum + row.count, 0),
    byPeriod: byPeriod.filter((row) => row.count > 0),
    estimatedMonthly: estimate('perMonth'),
    estimatedYearly: estimate('perYear'),
  }
}
