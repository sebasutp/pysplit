import { describe, expect, it } from 'vitest'

import { groupExpensesByDate } from './date-groups'

/** @param {number} daysAgo */
function isoDaysAgo(daysAgo) {
  const date = new Date()
  date.setUTCDate(date.getUTCDate() - daysAgo)
  return date.toISOString().slice(0, 10)
}

describe('groupExpensesByDate', () => {
  it('does not mutate the API expense objects', () => {
    const expenses = [
      { id: '1', title: 'Today', expense_date: isoDaysAgo(0) },
      { id: '2', title: 'Older', expense_date: isoDaysAgo(400) },
    ]
    const before = JSON.parse(JSON.stringify(expenses))

    const groups = groupExpensesByDate(expenses, 'en-US')

    expect(expenses).toEqual(before)
    expect(expenses[0]).not.toHaveProperty('_groupLabel')
    expect(groups[0].expenses[0]).not.toBe(expenses[0])
    expect(groups[0].expenses[0]._groupLabel).toBe('Today')
    expect(groups.flatMap((group) => group.expenses)).toHaveLength(2)
  })

  it('formats non-today rows without changing their ids', () => {
    const expenses = [{ id: '1', title: 'Past', expense_date: '2019-03-04' }]
    const groups = groupExpensesByDate(expenses, 'en-US')

    expect(groups[0].expenses[0].id).toBe('1')
    expect(groups[0].expenses[0]._groupLabel).toContain('2019')
  })
})
