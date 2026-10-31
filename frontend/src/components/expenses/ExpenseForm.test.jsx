import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { today } from '../../hooks/useExpenseForm'
import { ToastProvider } from '../../hooks/useToast'
import { ExpenseForm } from './ExpenseForm'

const { create, update, pendingTotal, clearPendingTotal } = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  pendingTotal: vi.fn(),
  clearPendingTotal: vi.fn(),
}))

vi.mock('../../services/repository', () => ({
  repository: {
    expenses: {
      create,
      update,
      remove: vi.fn(),
    },
    attachments: {
      upload: vi.fn(),
      update: vi.fn(),
      link: vi.fn(),
      remove: vi.fn(),
      extractTotal: vi.fn(),
      extractItems: vi.fn(),
      pendingTotal,
      clearPendingTotal,
    },
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

const expense = {
  id: 'expense-1',
  title: 'Hotel',
  amount: 3000,
  expense_date: '2026-10-01',
  category_id: 9,
  paid_by_id: 'p1',
  split_mode: 'EVENLY',
  recurrence_rule: 'NONE',
  notes: '',
  is_reimbursement: false,
  paid_for: [
    { participant_id: 'p1', shares: 1 },
    { participant_id: 'p2', shares: 1 },
  ],
  original_currency: null,
  original_amount: null,
  conversion_rate: null,
  version: 7,
  attachments: [],
}

beforeEach(() => {
  localStorage.clear()
  create.mockReset().mockResolvedValue({ id: 'expense-1' })
  update.mockReset()
  pendingTotal.mockReset().mockResolvedValue(null)
  clearPendingTotal.mockReset().mockResolvedValue(undefined)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
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

  it('keeps the repayment transfer amount in sync when the group amount changes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ rates: { USD: 2 } }),
      }),
    )
    const user = userEvent.setup()
    render(
      <MemoryRouter
        initialEntries={[
          '/groups/group-1/expenses/create?reimbursement=yes&from=p1&to=p2&amount=10000',
        ]}
      >
        <ToastProvider>
          <ExpenseForm group={group} categories={categories} activeUserId="p1" />
        </ToastProvider>
      </MemoryRouter>,
    )

    // The group currency is selected initially, so switch to a foreign one.
    await user.click(screen.getByLabelText('Currency of expense'))
    await user.click(screen.getByRole('option', { name: 'Euro (EUR)' }))

    const transfer = await screen.findByLabelText('Amount to transfer')
    await waitFor(() => expect(transfer).toHaveValue('50.00'))

    // Editing the authoritative group-currency amount must refresh the
    // read-only transfer amount immediately.
    const amount = screen.getByLabelText('Amount')
    await user.clear(amount)
    await user.type(amount, '120')
    await waitFor(() => expect(transfer).toHaveValue('60.00'))

    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create).toHaveBeenCalledWith(
      'group-1',
      expect.objectContaining({
        amount: 12000,
        original_amount: 6000,
        original_currency: 'EUR',
        conversion_rate: '2',
      }),
    )
  })

  it('submits the loaded version when editing an expense', async () => {
    update.mockResolvedValue({ ...expense })
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/groups/group-1/expenses/expense-1/edit']}>
        <ToastProvider>
          <ExpenseForm group={group} categories={categories} expense={expense} activeUserId="p1" />
        </ToastProvider>
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(update).toHaveBeenCalled())
    expect(update).toHaveBeenCalledWith(
      'group-1',
      'expense-1',
      expect.objectContaining({ title: 'Hotel', base_version: 7 }),
    )
  })

  it('does not send a version when creating an expense', async () => {
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
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(create).toHaveBeenCalled())
    expect(create.mock.calls[0][1]).not.toHaveProperty('base_version')
  })

  it('offers “Assign items” next to the advanced split options when a receipt exists', async () => {
    const user = userEvent.setup()
    const withReceipt = {
      ...expense,
      attachments: [
        {
          id: 'attachment-1',
          filename: 'receipt.jpg',
          content_type: 'image/jpeg',
          receipt_status: 'EXTRACTED',
          url: '/uploads/receipt.jpg',
        },
      ],
    }
    render(
      <MemoryRouter initialEntries={['/groups/group-1/expenses/expense-1/edit']}>
        <ToastProvider>
          <Routes>
            <Route
              path="/groups/group-1/expenses/expense-1/edit"
              element={
                <ExpenseForm
                  group={group}
                  categories={categories}
                  expense={withReceipt}
                  activeUserId="p1"
                />
              }
            />
            <Route path="/groups/group-1/expenses/expense-1/items" element={<div>items screen</div>} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    )

    const assignButtons = screen.getAllByRole('button', { name: 'Assign items' })
    expect(assignButtons).toHaveLength(2)
    await user.click(assignButtons[0])
    expect(await screen.findByText('items screen')).toBeInTheDocument()
  })

  it('shows a conflict message and stays on the form when the update is rejected', async () => {
    update.mockRejectedValue({ code: 'conflict', status: 409, detail: 'version mismatch' })
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/groups/group-1/expenses/expense-1/edit']}>
        <Routes>
          <Route
            path="/groups/group-1/expenses/expense-1/edit"
            element={
              <ToastProvider>
                <ExpenseForm
                  group={group}
                  categories={categories}
                  expense={expense}
                  activeUserId="p1"
                />
              </ToastProvider>
            }
          />
          <Route path="*" element={<div>left form</div>} />
        </Routes>
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: 'Save' }))

    const message =
      'This expense was changed by someone else. Reload the page and try again.'
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(message)
    expect((await screen.findByRole('status'))).toHaveTextContent(message)

    // No auto-retry and no navigation; the user's values are still editable.
    expect(update).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('left form')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Expense title')).toHaveValue('Hotel')
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()
  })

  it('surfaces and consumes a queued total-only receipt scan', async () => {
    pendingTotal.mockResolvedValue({
      amount: 42.5,
      title: 'Lunch',
      date: '2026-10-01',
      category_id: '9',
    })
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/groups/group-1/expenses/create']}>
        <ToastProvider>
          <ExpenseForm group={group} categories={categories} />
        </ToastProvider>
      </MemoryRouter>,
    )

    expect(
      await screen.findByText('A receipt scanned while offline is ready.'),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Use scanned total' }))

    expect(screen.getByLabelText('Expense title')).toHaveValue('Lunch')
    expect(screen.getByLabelText('Amount')).toHaveValue('42.50')
    expect(clearPendingTotal).toHaveBeenCalledWith('group-1')
    expect(
      screen.queryByText('A receipt scanned while offline is ready.'),
    ).not.toBeInTheDocument()
  })

  it('uses the local calendar date for the default expense date', () => {
    vi.stubEnv('TZ', 'America/Los_Angeles')
    vi.useFakeTimers()
    try {
      // 00:30 UTC is still the previous evening in Los Angeles. A UTC-based
      // `toISOString()` slice would report 2026-10-25 instead of 2026-10-24.
      vi.setSystemTime(new Date('2026-10-25T00:30:00Z'))
      expect(today()).toBe('2026-10-24')
    } finally {
      vi.useRealTimers()
    }
  })
})
