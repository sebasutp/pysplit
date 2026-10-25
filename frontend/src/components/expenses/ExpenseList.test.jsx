import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import '../../services/i18n'
import { ToastProvider } from '../../hooks/useToast'
import { ExpenseList } from './ExpenseList'

const { list, categoriesList } = vi.hoisted(() => ({
  list: vi.fn(),
  categoriesList: vi.fn(),
}))

vi.mock('../../services/repository', () => ({
  repository: {
    expenses: { list },
    categories: { list: categoriesList },
    exports: { csv: vi.fn(), json: vi.fn() },
  },
}))

const today = new Date().toISOString().slice(0, 10)

const group = {
  id: 'group-1',
  name: 'Trip',
  currency: '$',
  currency_code: 'USD',
  participants: [{ id: 'p1', name: 'Alice' }],
}

/** @param {string} id @param {string} title */
function expense(id, title) {
  return {
    id,
    title,
    expense_date: today,
    amount: 1000,
    paid_by_id: 'p1',
    paid_for: [{ participant_id: 'p1' }],
  }
}

beforeEach(() => {
  list.mockReset()
  categoriesList.mockReset()
  categoriesList.mockResolvedValue({ items: [] })
})

describe('ExpenseList pagination', () => {
  it('loads the next page and keeps the count text', async () => {
    list.mockImplementation((_groupId, options) => {
      if (options.offset === 0) {
        return Promise.resolve({
          items: [expense('e1', 'Lunch'), expense('e2', 'Dinner')],
          total: 3,
        })
      }
      return Promise.resolve({ items: [expense('e3', 'Taxi')], total: 3 })
    })

    render(
      <MemoryRouter>
        <ToastProvider>
          <ExpenseList group={group} activeUserId={null} />
        </ToastProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByText('Lunch')).toBeInTheDocument()
    expect(screen.getByText(/Showing 2 of 3 expenses/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Load more' }))

    expect(await screen.findByText('Taxi')).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
    expect(list.mock.calls[1][1]).toMatchObject({ limit: 100, offset: 2 })
  })

  it('debounces the search query', async () => {
    list.mockResolvedValue({ items: [expense('e1', 'Lunch')], total: 1 })

    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <ToastProvider>
          <ExpenseList group={group} activeUserId={null} />
        </ToastProvider>
      </MemoryRouter>,
    )

    await screen.findByText('Lunch')
    expect(list).toHaveBeenCalledTimes(1)

    await user.type(screen.getByLabelText('Search expenses'), 'pizza')
    expect(list).toHaveBeenCalledTimes(1)

    await waitFor(
      () => {
        expect(list).toHaveBeenCalledTimes(2)
        expect(list.mock.calls[1][1]).toMatchObject({ q: 'pizza' })
      },
      { timeout: 2000 },
    )
  })
})
