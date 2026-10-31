import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import '../../services/i18n'
import { ToastProvider } from '../../hooks/useToast'
import { ReceiptItemsPage } from './ReceiptItemsPage'

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

vi.mock('../../hooks/useFeatures', () => ({
  useFeatures: () => ({ features: { receipt_ai: false }, loading: false }),
}))

vi.mock('../../services/repository', () => ({
  repository: { expenses: { get }, attachments: {} },
}))

beforeEach(() => {
  get.mockReset()
})

describe('ReceiptItemsPage', () => {
  it('aborts the in-flight expense request on unmount', async () => {
    /** @type {AbortSignal|undefined} */
    let capturedSignal
    get.mockImplementation(
      (_groupId, _expenseId, options) =>
        new Promise(() => {
          capturedSignal = options?.signal
        }),
    )

    const { unmount } = render(
      <MemoryRouter initialEntries={['/groups/g1/expenses/e1/items']}>
        <ToastProvider>
          <Routes>
            <Route path="/groups/:groupId/expenses/:expenseId/items" element={<ReceiptItemsPage />} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('status')).toBeInTheDocument()
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1))
    expect(capturedSignal?.aborted).toBe(false)

    unmount()
    expect(capturedSignal?.aborted).toBe(true)
  })
})
