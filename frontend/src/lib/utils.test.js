import { describe, expect, it } from 'vitest'

import { formatCurrency, majorUnits, parseAmount } from '../utils/currency'
import { groupExpensesByDate } from '../utils/date-groups'

describe('frontend formatting utilities', () => {
  it('formats amounts and dates', () => {
    expect(formatCurrency({ code: 'USD', symbol: '$' }, 12345)).toBe('$123.45')
    expect(formatCurrency({ code: 'EUR', symbol: '€' }, -500)).toBe('-€5.00')
    expect(formatCurrency({ code: '', symbol: 'kr' }, 12345)).toBe('kr123.45')
    expect(majorUnits(12345)).toBe('123.45')
    expect(majorUnits(1200)).toBe('12')
    expect(parseAmount('12,34')).toBe(1234)

    const groups = groupExpensesByDate([
      { id: '1', expense_date: new Date().toISOString().slice(0, 10) },
    ])
    expect(groups[0].key).toBe('today')
    expect(groups[0].expenses).toHaveLength(1)
  })
})
