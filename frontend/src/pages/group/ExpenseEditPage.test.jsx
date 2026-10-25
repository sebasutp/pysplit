import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import '../../services/i18n'
import { ToastProvider } from '../../hooks/useToast'
import { ExpenseEditPage } from './ExpenseEditPage'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))

const group = {
  id: 'g1',
  name: 'Trip',
  currency: '$',
  currency_code: 'USD',
  participants: [{ id: 'p1', name: 'Alice' }],
}

vi.mock('../../components/groups/GroupLayout', () => ({
  useGroupContext: () => ({ group }),
}))

vi.mock('../../hooks/useCategories', () => ({
  useCategories: () => ({ categories: [], loading: false }),
}))

vi.mock('../../hooks/useFeatures', () => ({
  useFeatures: () => ({ features: {}, loading: false }),
}))

vi.mock('../../services/repository', () => ({
  repository: { expenses: { get } },
}))

/** @param {string} id @param {string} title */
function expense(id, title) {
  return {
    id,
    title,
    amount: 1000,
    expense_date: '2024-01-01',
    paid_by_id: 'p1',
    paid_for: [{ participant_id: 'p1' }],
  }
}

/** @param {{to: string|null}} props */
function GoTo({ to }) {
  const navigate = useNavigate()
  useEffect(() => {
    if (to) navigate(to)
  }, [navigate, to])
  return null
}

/** @param {{to: string|null}} props */
function Harness({ to }) {
  return (
    <MemoryRouter initialEntries={['/groups/g1/expenses/a/edit']}>
      <ToastProvider>
        <Routes>
          <Route
            path="/groups/:groupId/expenses/:expenseId/edit"
            element={
              <>
                <ExpenseEditPage />
                <GoTo to={to} />
              </>
            }
          />
        </Routes>
      </ToastProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  get.mockReset()
})

describe('ExpenseEditPage', () => {
  it('clears the previous expense when the id changes', async () => {
    /** @type {(value: any) => void} */
    let resolveB
    get.mockImplementation((_groupId, expenseId) => {
      if (expenseId === 'a') return Promise.resolve(expense('a', 'Old expense'))
      return new Promise((resolve) => {
        resolveB = resolve
      })
    })

    const { rerender } = render(<Harness to={null} />)
    expect(await screen.findByDisplayValue('Old expense')).toBeInTheDocument()

    rerender(<Harness to="/groups/g1/expenses/b/edit" />)
    await waitFor(() => expect(get).toHaveBeenCalledWith('g1', 'b', expect.anything()))

    expect(screen.queryByDisplayValue('Old expense')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()

    await act(async () => {
      resolveB(expense('b', 'New expense'))
    })
    expect(await screen.findByDisplayValue('New expense')).toBeInTheDocument()
  })
})
