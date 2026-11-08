import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import '../../services/i18n'
import { ToastProvider } from '../../hooks/useToast'
import { ReceiptItemsPage } from './ReceiptItemsPage'

const { get, getAttachment, setPortions } = vi.hoisted(() => ({
  get: vi.fn(),
  getAttachment: vi.fn(),
  setPortions: vi.fn(),
}))

const group = {
  id: 'g1',
  name: 'Trip',
  currency: '$',
  currency_code: 'USD',
  participants: [
    { id: 'p1', name: 'Alice' },
    { id: 'p2', name: 'Bob' },
  ],
}

vi.mock('../../components/groups/GroupLayout', () => ({
  useGroupContext: () => ({ group }),
}))

vi.mock('../../hooks/useFeatures', () => ({
  useFeatures: () => ({ features: { receipt_ai: true }, loading: false }),
}))

vi.mock('../../services/repository', () => ({
  repository: {
    expenses: { get },
    attachments: { get: getAttachment, setPortions },
  },
}))

const expense = {
  id: 'e1',
  amount: 1500,
  attachments: [{ id: 'a1', receipt_status: 'EXTRACTED' }],
}

/** @param {any} overrides */
function makeItem(overrides = {}) {
  return {
    id: 'i1',
    name: 'Beer',
    quantity_milli: 3000,
    amount: 1500,
    is_shared: false,
    portions: [],
    ...overrides,
  }
}

/** @param {any|any[]} items */
function makeState(items) {
  const list = Array.isArray(items) ? items : [items]
  return {
    attachment: {
      id: 'a1',
      receipt_status: 'EXTRACTED',
      merchant: 'Mock Trattoria',
      content_type: 'image/png',
      url: 'local-receipt.png',
      total: list.reduce((sum, item) => sum + item.amount, 0),
    },
    items: list,
    opt_outs: [],
    split: {
      items_total: list.reduce((sum, item) => sum + item.amount, 0),
      participants: [],
    },
  }
}

/** @param {any|any[]} items */
function mockLoaded(items) {
  get.mockResolvedValue(expense)
  getAttachment.mockResolvedValue(makeState(items))
  setPortions.mockResolvedValue(makeState(items))
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/groups/g1/expenses/e1/items']}>
      <ToastProvider>
        <Routes>
          <Route path="/groups/:groupId/expenses/:expenseId/items" element={<ReceiptItemsPage />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  get.mockReset()
  getAttachment.mockReset()
  setPortions.mockReset()
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

    const { unmount } = renderPage()

    expect(await screen.findByRole('status')).toBeInTheDocument()
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1))
    expect(capturedSignal?.aborted).toBe(false)

    unmount()
    expect(capturedSignal?.aborted).toBe(true)
  })

  it('assigns unit quantities to multiple participants', async () => {
    const user = userEvent.setup()
    mockLoaded(makeItem({ quantity_milli: 3000, amount: 1500 }))

    renderPage()

    await screen.findByText('Beer')
    await user.click(screen.getByRole('button', { name: /^Assign Beer for / }))

    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Alice'), '2')
    await user.type(within(dialog).getByLabelText('Bob'), '1')

    await user.click(within(dialog).getByRole('button', { name: 'Assign' }))

    await waitFor(() =>
      expect(setPortions).toHaveBeenCalledWith('g1', 'a1', 'i1', [
        { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 2000 },
        { target: 'PARTICIPANT', participant_id: 'p2', quantity_milli: 1000 },
      ]),
    )
  })

  it('assigns fractional unit quantities to multiple participants', async () => {
    const user = userEvent.setup()
    mockLoaded(makeItem({ quantity_milli: 1000, amount: 500 }))

    renderPage()

    await screen.findByText('Beer')
    await user.click(screen.getByRole('button', { name: /^Assign Beer for / }))

    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Alice'), '0.5')
    await user.type(within(dialog).getByLabelText('Bob'), '0.5')

    await user.click(within(dialog).getByRole('button', { name: 'Assign' }))

    await waitFor(() =>
      expect(setPortions).toHaveBeenCalledWith('g1', 'a1', 'i1', [
        { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 500 },
        { target: 'PARTICIPANT', participant_id: 'p2', quantity_milli: 500 },
      ]),
    )
  })

  it('prefills existing portions when opening the dialog', async () => {
    const user = userEvent.setup()
    mockLoaded(
      makeItem({
        portions: [
          { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 2000 },
          { target: 'PARTICIPANT', participant_id: 'p2', quantity_milli: 1000 },
        ],
      }),
    )

    renderPage()

    await screen.findByRole('heading', { name: 'Alice' })
    await user.click(screen.getByRole('button', { name: /^Assign Beer for / }))

    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('Alice')).toHaveValue(2)
    expect(within(dialog).getByLabelText('Bob')).toHaveValue(1)
  })

  it('disables assignment when quantities exceed the item', async () => {
    const user = userEvent.setup()
    mockLoaded(makeItem({ quantity_milli: 1000, amount: 500 }))

    renderPage()

    await screen.findByText('Beer')
    await user.click(screen.getByRole('button', { name: /^Assign Beer for / }))

    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Alice'), '2')

    expect(within(dialog).getByRole('alert')).toHaveTextContent('exceeds')
    expect(within(dialog).getByRole('button', { name: 'Assign' })).toBeDisabled()
  })

  it('clears existing assignments', async () => {
    const user = userEvent.setup()
    mockLoaded(
      makeItem({
        portions: [
          { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 2000 },
          { target: 'PARTICIPANT', participant_id: 'p2', quantity_milli: 1000 },
        ],
      }),
    )

    renderPage()

    await screen.findByRole('heading', { name: 'Alice' })
    await user.click(screen.getByRole('button', { name: /^Assign Beer for / }))

    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Remove portion' }))

    await waitFor(() => expect(setPortions).toHaveBeenCalledWith('g1', 'a1', 'i1', []))
  })

  it('clears a shared item back to unassigned', async () => {
    const user = userEvent.setup()
    const sharedItem = makeItem({
      name: 'Shared item',
      quantity_milli: 2000,
      amount: 1000,
      is_shared: true,
    })
    get.mockResolvedValue(expense)
    getAttachment.mockResolvedValue(makeState(sharedItem))
    setPortions.mockResolvedValue(makeState({ ...sharedItem, is_shared: false, portions: [] }))

    renderPage()

    await screen.findByText('Shared item')
    expect(screen.getByRole('heading', { name: 'Shared' })).toBeInTheDocument()
    expect(screen.getByText('2 of 2')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Assign Shared item for / }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Remove portion' }))

    await waitFor(() => expect(setPortions).toHaveBeenCalledWith('g1', 'a1', 'i1', []))
    expect(await screen.findByRole('heading', { name: 'Unassigned' })).toBeInTheDocument()
    expect(screen.getByText('2 left')).toBeInTheDocument()
    const clearedRow = /** @type {HTMLElement} */ (screen.getByText('Shared item').closest('li'))
    expect(within(clearedRow).getByText('$10.00')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Shared' })).not.toBeInTheDocument()
  })

  it('assigns participant and shared quantities together', async () => {
    const user = userEvent.setup()
    const mixedItem = makeItem({ quantity_milli: 3000, amount: 1350 })
    get.mockResolvedValue(expense)
    getAttachment.mockResolvedValue(makeState(mixedItem))
    setPortions.mockResolvedValue(
      makeState({
        ...mixedItem,
        portions: [
          { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 2000 },
          { target: 'SHARED', participant_id: null, quantity_milli: 1000 },
        ],
      }),
    )

    renderPage()

    await screen.findByText('Beer')
    await user.click(screen.getByRole('button', { name: /^Assign Beer for / }))

    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByLabelText('Alice'), '2')
    await user.type(within(dialog).getByLabelText('Shared'), '1')

    await user.click(within(dialog).getByRole('button', { name: 'Assign' }))

    await waitFor(() =>
      expect(setPortions).toHaveBeenCalledWith('g1', 'a1', 'i1', [
        { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 2000 },
        { target: 'SHARED', participant_id: null, quantity_milli: 1000 },
      ]),
    )
    expect(await screen.findByRole('heading', { name: 'Alice' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Shared' })).toBeInTheDocument()
    expect(screen.getByText('2 of 3')).toBeInTheDocument()
    expect(screen.getByText('1 of 3')).toBeInTheDocument()
    expect(screen.getByText('$9.00')).toBeInTheDocument()
    expect(screen.getByText('$4.50')).toBeInTheDocument()
  })

  it('lists each person as a separate row with their own quantity and amount', async () => {
    mockLoaded(
      makeItem({
        quantity_milli: 3000,
        amount: 1350,
        portions: [
          { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 2000 },
          { target: 'PARTICIPANT', participant_id: 'p2', quantity_milli: 1000 },
        ],
      }),
    )

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Alice' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Bob' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Alice, Bob' })).not.toBeInTheDocument()
    expect(screen.getByText('2 of 3')).toBeInTheDocument()
    expect(screen.getByText('1 of 3')).toBeInTheDocument()
    expect(screen.getByText('$9.00')).toBeInTheDocument()
    expect(screen.getByText('$4.50')).toBeInTheDocument()
    expect(screen.getAllByText('Beer')).toHaveLength(2)
  })

  it('shows fractional quantities per person', async () => {
    mockLoaded(
      makeItem({
        quantity_milli: 1000,
        amount: 1350,
        portions: [
          { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 500 },
          { target: 'PARTICIPANT', participant_id: 'p2', quantity_milli: 500 },
        ],
      }),
    )

    renderPage()

    expect(await screen.findAllByText('0.5 of 1')).toHaveLength(2)
    expect(screen.getAllByText('$6.75')).toHaveLength(2)
  })

  it('shows the unassigned remainder as its own row', async () => {
    mockLoaded(
      makeItem({
        quantity_milli: 3000,
        amount: 1350,
        portions: [{ target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 1000 }],
      }),
    )

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Alice' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Unassigned' })).toBeInTheDocument()
    expect(screen.getByText('1 of 3')).toBeInTheDocument()
    expect(screen.getByText('2 left')).toBeInTheDocument()
    expect(screen.getByText('$4.50')).toBeInTheDocument()
    expect(screen.getByText('$9.00')).toBeInTheDocument()
  })

  it('sums duplicate portions in rows and when prefilling the dialog', async () => {
    const user = userEvent.setup()
    mockLoaded(
      makeItem({
        quantity_milli: 3000,
        amount: 1350,
        portions: [
          { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 1000 },
          { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 1000 },
          { target: 'PARTICIPANT', participant_id: 'p2', quantity_milli: 1000 },
        ],
      }),
    )

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Alice' })).toBeInTheDocument()
    expect(screen.getByText('2 of 3')).toBeInTheDocument()
    expect(screen.getByText('1 of 3')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Assign Beer for / }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText('Alice')).toHaveValue(2)
    expect(within(dialog).getByLabelText('Bob')).toHaveValue(1)
  })

  it('renders whole-item actions once for an item in multiple sections', async () => {
    mockLoaded(
      makeItem({
        quantity_milli: 3000,
        amount: 1350,
        portions: [
          { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 2000 },
          { target: 'PARTICIPANT', participant_id: 'p2', quantity_milli: 1000 },
        ],
      }),
    )

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Alice' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^Assign Beer for / })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: /^Edit Beer for / })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: /^Delete Beer for / })).toHaveLength(1)
  })

  it('does not prefill Shared for is_shared items with unknown or zero portions', async () => {
    const user = userEvent.setup()
    mockLoaded(
      makeItem({
        quantity_milli: 1000,
        amount: 1000,
        is_shared: true,
        portions: [
          { target: 'PARTICIPANT', participant_id: 'stranger', quantity_milli: 1000 },
          { target: 'PARTICIPANT', participant_id: 'p1', quantity_milli: 0 },
        ],
      }),
    )

    renderPage()

    await screen.findByRole('heading', { name: 'Unassigned' })
    await user.click(screen.getByRole('button', { name: /^Assign Beer for / }))
    const dialog = await screen.findByRole('dialog')
    expect(/** @type {HTMLInputElement} */ (within(dialog).getByLabelText('Shared')).value).toBe('')
    expect(/** @type {HTMLInputElement} */ (within(dialog).getByLabelText('Alice')).value).toBe('')
    expect(/** @type {HTMLInputElement} */ (within(dialog).getByLabelText('Bob')).value).toBe('')
  })

  it('shows an is_shared item without portions in the Shared section', async () => {
    mockLoaded(makeItem({ quantity_milli: 1000, amount: 1000, is_shared: true }))

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Shared' })).toBeInTheDocument()
    const row = /** @type {HTMLElement} */ (screen.getByText('Beer').closest('li'))
    expect(within(row).getByText('1 of 1')).toBeInTheDocument()
    expect(within(row).getByText('$10.00')).toBeInTheDocument()
  })
})
