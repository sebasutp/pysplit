/**
 * Group balance and reimbursement math.
 *
 * Pure JavaScript mirror of `backend/app/utils/balances.py`. Amounts are
 * integer minor units; positive totals mean the participant is owed money.
 */

import { getExpenseShares } from './shares'

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
 * @param {any[]} expenses
 * @returns {Map<string, {paid: number, paidFor: number, total: number}>}
 */
export function getBalances(expenses) {
  /** @type {Map<string, {paid: number, paidFor: number, total: number}>} */
  const balances = new Map()

  /** @param {string} participantId */
  function entry(participantId) {
    let value = balances.get(participantId)
    if (!value) {
      value = { paid: 0, paidFor: 0, total: 0 }
      balances.set(participantId, value)
    }
    return value
  }

  for (const expense of expenses) {
    const payer = paidById(expense)
    entry(payer).paid += Number(expense.amount)
    for (const [participantId, amount] of getExpenseShares(expense)) {
      entry(participantId).paidFor += amount
    }
  }

  for (const values of balances.values()) {
    values.paid = Math.round(values.paid) + 0
    values.paidFor = Math.round(values.paidFor) + 0
    values.total = values.paid - values.paidFor
  }
  return balances
}

/**
 * @param {{from: string, to: string, amount: number}[]} reimbursements
 * @returns {Map<string, {paid: number, paidFor: number, total: number}>}
 */
export function getPublicBalances(reimbursements) {
  /** @type {Map<string, {paid: number, paidFor: number, total: number}>} */
  const balances = new Map()
  /** @param {string} participantId */
  function entry(participantId) {
    let value = balances.get(participantId)
    if (!value) {
      value = { paid: 0, paidFor: 0, total: 0 }
      balances.set(participantId, value)
    }
    return value
  }

  for (const reimbursement of reimbursements) {
    const source = String(reimbursement.from)
    const target = String(reimbursement.to)
    const amount = Number(reimbursement.amount)
    entry(source).paidFor += amount
    entry(source).total -= amount
    entry(target).paid += amount
    entry(target).total += amount
  }
  return balances
}

/**
 * Stable comparator: positive balances before negative, then by id.
 *
 * @param {{participantId: string, total: number}} first
 * @param {{participantId: string, total: number}} second
 * @returns {number}
 */
function compareForReimbursements(first, second) {
  if (first.total > 0 && second.total < 0) return -1
  if (second.total > 0 && first.total < 0) return 1
  return first.participantId < second.participantId ? -1 : 1
}

/**
 * @param {Map<string, {total: number}>|Record<string, {total: number}>} balances
 * @returns {{from: string, to: string, amount: number}[]}
 */
export function getSuggestedReimbursements(balances) {
  const entries = []
  const source =
    balances instanceof Map ? [...balances.entries()] : Object.entries(balances)
  for (const [participantId, values] of source) {
    if (Number(values.total) !== 0) {
      entries.push({ participantId, total: Number(values.total) })
    }
  }
  entries.sort(compareForReimbursements)

  /** @type {{from: string, to: string, amount: number}[]} */
  const reimbursements = []
  while (entries.length > 1) {
    const first = entries[0]
    const last = entries[entries.length - 1]

    if (first.total > -last.total) {
      reimbursements.push({ from: last.participantId, to: first.participantId, amount: -last.total })
      first.total += last.total
      entries.pop()
    } else {
      reimbursements.push({ from: last.participantId, to: first.participantId, amount: first.total })
      last.total = first.total + last.total
      entries.shift()
    }
  }
  return reimbursements.filter((row) => Number(row.amount) !== 0)
}
