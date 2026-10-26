import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import {
  getBalances,
  getPublicBalances,
  getSuggestedReimbursements,
} from './balances'
import {
  formatAmountAsDecimal,
  formatAmountForCsv,
} from './currency'
import { computeReceiptSplit } from './receipt-split'
import { calculateNextDate } from './recurrence'
import { getExpenseShares } from './shares'
import {
  filterExpensesByDateRange,
  getExpensesByCategory,
  getExpensesByMonth,
  getRecurringSpending,
  getSpendingByCategory,
  getSpendingByParticipant,
  getSpendingOverTime,
  getSpendingSummary,
  getTotalActiveUserPaidFor,
  getTotalActiveUserShare,
  getTotalGroupSpending,
} from './totals'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../../..')
const fixtures = resolve(root, 'shared/fixtures/domain')

/** @param {string} name */
function load(name) {
  return JSON.parse(readFileSync(resolve(fixtures, name), 'utf8'))
}

/** @param {Map<string, any>} map */
function mapToObject(map) {
  return Object.fromEntries([...map.entries()].sort(([first], [second]) => (first < second ? -1 : 1)))
}

describe('JavaScript domain mirrors replay the Python fixtures', () => {
  it('splits shares exactly', () => {
    for (const fixture of load('shares.json')) {
      const result = Object.fromEntries(
        [...getExpenseShares(fixture.expense).entries()].sort(([first], [second]) =>
          first < second ? -1 : 1,
        ),
      )
      expect(result, fixture.name).toEqual(fixture.expected)
    }
  })

  it('computes balances and reimbursements', () => {
    for (const fixture of load('balances.json')) {
      const balances = getBalances(fixture.expenses)
      const reimbursements = getSuggestedReimbursements(balances)
      const publicBalances = getPublicBalances(reimbursements)
      expect(mapToObject(balances), fixture.name).toEqual(fixture.expected.balances)
      expect(reimbursements, fixture.name).toEqual(fixture.expected.reimbursements)
      expect(mapToObject(publicBalances), fixture.name).toEqual(fixture.expected.public)
    }
  })

  it('computes spending statistics', () => {
    const fixture = load('totals.json')
    const expenses = fixture.expenses
    const participants = fixture.participants
    const expected = fixture.expected

    expect(getTotalGroupSpending(expenses)).toBe(expected.total_group_spending)
    expect(getTotalActiveUserPaidFor('alice', expenses)).toBe(
      expected.total_active_user_paid_for,
    )
    expect(getTotalActiveUserShare('alice', expenses)).toBe(expected.total_active_user_share)
    expect(getSpendingByCategory(expenses)).toEqual(expected.spending_by_category)
    expect(getSpendingByParticipant(participants, expenses)).toEqual(
      expected.spending_by_participant,
    )
    expect(getSpendingOverTime(expenses)).toEqual(expected.spending_over_time)
    expect(getSpendingSummary(expenses)).toEqual(expected.summary)
    expect(getRecurringSpending(expenses)).toEqual(expected.recurring)
    expect(
      filterExpensesByDateRange(expenses, '2026-02-01', '2026-02-28').map((row) => row.id),
    ).toEqual(expected.range_2026_02)
    expect(getExpensesByCategory(expenses, 9).map((row) => row.id)).toEqual(
      expected.category_9,
    )
    expect(getExpensesByMonth(expenses, '2026-01').map((row) => row.id)).toEqual(
      expected.month_2026_01,
    )
  })

  it('allocates receipt items including opt-outs and unassigned amounts', () => {
    for (const fixture of load('receipt-split.json')) {
      expect(
        computeReceiptSplit(fixture.participants, fixture.opt_outs, fixture.items),
        fixture.name,
      ).toEqual(fixture.expected)
    }
  })

  it('advances recurrence with the reference clamp', () => {
    for (const fixture of load('recurrence.json')) {
      expect(calculateNextDate(fixture.rule, fixture.prior).toISOString().replace('.000Z', 'Z'), fixture.rule).toBe(
        fixture.expected,
      )
    }
  })

  it('formats minor units for display and CSV', () => {
    for (const fixture of load('currency.json')) {
      expect(formatAmountAsDecimal(fixture.amount, fixture.currency_code)).toBe(
        fixture.decimal,
      )
      expect(formatAmountForCsv(fixture.amount, fixture.currency_code)).toBe(fixture.csv)
    }
  })
})
