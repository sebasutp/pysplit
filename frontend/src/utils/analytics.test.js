import { describe, expect, it } from 'vitest'

import { anonymizePath } from './analytics'

describe('anonymizePath', () => {
  it('anonymizes group and expense ids', () => {
    expect(anonymizePath('/groups/abc123/expenses/xyz789/edit?secret=1')).toBe(
      '/groups/[groupId]/expenses/[expenseId]/edit',
    )
    expect(anonymizePath('/groups/abc123/receipts/rcpt')).toBe(
      '/groups/[groupId]/receipts/[receiptId]',
    )
  })

  it('leaves static paths intact', () => {
    expect(anonymizePath('/groups')).toBe('/groups')
  })
})
