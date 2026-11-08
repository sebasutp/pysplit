import { describe, expect, it } from 'vitest'

import { formatCurrency, majorUnits, parseAmount } from './currency'

/**
 * Build the expected zero-decimal currency string with Intl so the assertion
 * focuses on the number of fraction digits rather than the exact symbol.
 *
 * @param {string} code
 * @param {number} amount
 */
function zeroDecimalFormat(code, amount) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: code,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

describe('formatCurrency', () => {
  it('formats zero-decimal currencies without fractional digits', () => {
    expect(formatCurrency({ code: 'JPY', symbol: '¥' }, 1000)).toBe('¥1,000')
    expect(formatCurrency({ code: 'KRW', symbol: '₩' }, 1000)).toBe('₩1,000')

    const cop = formatCurrency({ code: 'COP', symbol: 'COL$' }, 1000)
    expect(cop).toBe(zeroDecimalFormat('COP', 1000))
    expect(cop).toContain('1,000')
  })

  it('keeps two decimals for USD and EUR', () => {
    expect(formatCurrency({ code: 'USD', symbol: '$' }, 12345)).toBe('$123.45')
    expect(formatCurrency({ code: 'EUR', symbol: '€' }, -500)).toBe('-€5.00')
    expect(formatCurrency({ code: 'EUR', symbol: '€' }, 123456, 'de-DE')).toContain(
      '1.234,56',
    )
  })

  it('still supports custom currencies with a symbol fallback', () => {
    expect(formatCurrency({ code: '', symbol: 'kr' }, 12345)).toBe('kr123.45')
  })
})

describe('majorUnits', () => {
  it('respects the currency decimal digits', () => {
    expect(majorUnits(1000, 'JPY')).toBe('1000')
    expect(majorUnits(1000, 'KRW')).toBe('1000')
    expect(majorUnits(1234, 'COP')).toBe('1234')
    expect(majorUnits(12345)).toBe('123.45')
    expect(majorUnits(1200)).toBe('12')
    expect(majorUnits(4250)).toBe('42.5')
    expect(majorUnits(0)).toBe('0')
    expect(majorUnits(null, 'JPY')).toBe('')
  })
})

describe('parseAmount', () => {
  it('parses grouping and decimal separators per locale', () => {
    expect(parseAmount('1,234.56', 'USD', 'en-US')).toBe(123456)
    expect(parseAmount('1.234,56', 'EUR', 'de-DE')).toBe(123456)
    expect(parseAmount('1 234,56', 'EUR', 'de-DE')).toBe(123456)
    expect(parseAmount('12,34', 'EUR', 'de-DE')).toBe(1234)
    expect(parseAmount('12.34', 'USD', 'en-US')).toBe(1234)
  })

  it('infers the decimal separator when no locale is given', () => {
    expect(parseAmount('1,234.56')).toBe(123456)
    expect(parseAmount('1.234,56')).toBe(123456)
    expect(parseAmount('12,34')).toBe(1234)
    expect(parseAmount('12.34')).toBe(1234)
  })

  it('uses zero decimals for zero-decimal currencies', () => {
    expect(parseAmount('1000', 'JPY')).toBe(1000)
    expect(parseAmount('1000', 'KRW')).toBe(1000)
    // A fractional minor unit is rounded to the nearest whole unit.
    expect(parseAmount('1.234', 'JPY')).toBe(1)
    // With a German locale the dots are grouping separators, so 1.234 = 1234.
    expect(parseAmount('1.234', 'JPY', 'de-DE')).toBe(1234)
    expect(parseAmount('100.5', 'JPY')).toBe(101)
  })

  it('handles signs and invalid input', () => {
    expect(parseAmount('-1,234.56', 'USD', 'en-US')).toBe(-123456)
    expect(parseAmount('', 'USD')).toBe(0)
    expect(parseAmount('abc', 'USD')).toBe(0)
  })
})
