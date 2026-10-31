import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import '../../services/i18n'
import { AttachmentList } from './AttachmentList'
import { ReceiptItemsPreview } from './ReceiptItemsPreview'

const receipt = {
  id: 'a1',
  filename: 'receipt.jpg',
  content_type: 'image/jpeg',
  byte_size: 1200,
  url: '/uploads/receipt.jpg',
  thumbnail_url: '/uploads/receipt-thumb.jpg',
  receipt_status: 'EXTRACTED',
}

describe('AttachmentList', () => {
  it('labels the receipt action “Assign items”', async () => {
    const user = userEvent.setup()
    const onReview = vi.fn()
    render(
      <AttachmentList attachments={[receipt]} onReview={onReview} canScan />,
    )

    await user.click(screen.getByRole('button', { name: 'Assign items' }))
    expect(onReview).toHaveBeenCalledWith(receipt)
    expect(screen.queryByRole('button', { name: 'Review items' })).not.toBeInTheDocument()
  })
})

describe('ReceiptItemsPreview', () => {
  it('shows extracted items before the expense is saved', () => {
    render(
      <ReceiptItemsPreview
        currency={{ code: 'USD', symbol: '$' }}
        receipt={{
          merchant: 'Mock Trattoria',
          total: 4850,
          items: [
            { id: 'i1', name: 'Margherita Pizza', amount: 1400 },
            { id: 'i2', name: 'Tiramisu', amount: 800 },
          ],
        }}
      />,
    )

    expect(screen.getByText(/AI extracted items/)).toBeInTheDocument()
    expect(screen.getByText('Margherita Pizza')).toBeInTheDocument()
    expect(screen.getByText('Tiramisu')).toBeInTheDocument()
    expect(
      screen.getByText('Save the expense to assign these items to participants.'),
    ).toBeInTheDocument()
  })
})
