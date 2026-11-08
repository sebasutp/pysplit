import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'

import { setLocale } from '../../services/i18n'
import { ExpenseCard } from './ExpenseCard'

const group = {
  id: 'group-1',
  name: 'Trip',
  currency: '$',
  currency_code: 'USD',
  participants: [{ id: 'p1', name: 'Alice' }],
}

const expense = {
  id: 'expense-1',
  title: 'Hotel',
  amount: 10000,
  expense_date: '2024-01-15',
  paid_by_id: 'p1',
  paid_for: [{ participant_id: 'p1' }],
  pending: true,
  attachments: [],
}

afterEach(async () => {
  await act(async () => {
    await setLocale('en-US')
  })
})

describe('ExpenseCard', () => {
  it('renders the pending marker and date in the active locale', async () => {
    await setLocale('de-DE')
    render(
      <MemoryRouter>
        <ExpenseCard
          expense={expense}
          participants={group.participants}
          categories={[]}
          group={group}
          activeUserId={null}
          locale="de-DE"
        />
      </MemoryRouter>,
    )

    expect(screen.getByText('Synchronisierung ausstehend')).toBeInTheDocument()
    expect(screen.getByText(/für alle/)).toBeInTheDocument()

    const formatted = new Intl.DateTimeFormat('de-DE', {
      dateStyle: 'medium',
      timeZone: 'UTC',
    }).format(new Date('2024-01-15T00:00:00Z'))
    expect(screen.getByText(formatted)).toBeInTheDocument()
    expect(screen.queryByText('2024-01-15')).not.toBeInTheDocument()
  })
})
