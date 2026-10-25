import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../../hooks/useToast'
import { ExpenseForm } from './ExpenseForm'

const { create, update } = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
}))

vi.mock('../../services/repository', () => ({
  repository: {
    expenses: {
      create,
      update,
      remove: vi.fn(),
    },
    documents: { upload: vi.fn(), remove: vi.fn() },
    receipts: { upload: vi.fn(), extractTotal: vi.fn() },
  },
}))

const group = {
  id: 'group-1',
  name: 'Trip',
  currency: '$',
  currency_code: 'USD',
  participants: [
    { id: 'p1', name: 'Alice' },
    { id: 'p2', name: 'Bob' },
  ],
}

const categories = [
  { id: 0, grouping: 'Uncategorized', name: 'General' },
  { id: 9, grouping: 'Food and Drink', name: 'Groceries' },
]

beforeEach(() => {
  localStorage.clear()
  create.mockReset().mockResolvedValue({ id: 'expense-1' })
  update.mockReset()
})

describe('ExpenseForm', () => {
  it('saves splitting defaults', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/groups/group-1/expenses/create']}>
        <ToastProvider>
          <ExpenseForm group={group} categories={categories} />
        </ToastProvider>
      </MemoryRouter>,
    )

    await user.type(screen.getByLabelText('Expense title'), 'Dinner')
    await user.type(screen.getByLabelText('Amount'), '30')
    await user.click(screen.getByRole('button', { name: /Advanced splitting options/ }))
    await user.click(
      screen.getByLabelText('Save as default splitting options'),
    )
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(create).toHaveBeenCalled())
    const saved = JSON.parse(
      localStorage.getItem('group-1-defaultSplittingOptions') || '{}',
    )
    expect(saved.splitMode).toBe('EVENLY')
    expect(saved.paidFor).toEqual(['p1', 'p2'])
  })
})
