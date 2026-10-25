import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ReceiptFooter } from './ReceiptFooter'

describe('ReceiptFooter', () => {
  it('renders provisional totals', () => {
    render(
      <ReceiptFooter
        split={{
          participants: [
            { participant_id: 'p1', total: 3000 },
            { participant_id: 'p2', total: 2000 },
          ],
          items_total: 5000,
          shared_pool: 0,
          unassigned_pool: 0,
          all_opted_out: false,
        }}
        currency={{ code: 'USD', symbol: '$' }}
        participants={[
          { id: 'p1', name: 'Alice' },
          { id: 'p2', name: 'Bob' },
        ]}
        onApply={vi.fn()}
      />,
    )

    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getAllByText('$50.00').length).toBeGreaterThan(0)
    expect(screen.getByText('Reconciles')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Apply to expense' }),
    ).toBeInTheDocument()
  })
})
