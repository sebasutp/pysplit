import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import '../../services/i18n'
import { AppRefreshCard } from './AppRefreshCard'

const { forceRefreshApp } = vi.hoisted(() => ({ forceRefreshApp: vi.fn() }))

vi.mock('../../services/pwa', () => ({ forceRefreshApp }))

beforeEach(() => {
  forceRefreshApp.mockReset()
  forceRefreshApp.mockResolvedValue(undefined)
})

describe('AppRefreshCard', () => {
  it('calls forceRefreshApp when the button is clicked', async () => {
    const user = userEvent.setup()
    render(<AppRefreshCard />)

    await user.click(screen.getByRole('button', { name: 'Refresh app' }))

    expect(forceRefreshApp).toHaveBeenCalledTimes(1)
  })

  it('re-enables the button when the refresh helper fails', async () => {
    const user = userEvent.setup()
    forceRefreshApp.mockRejectedValueOnce(new Error('refresh failed'))
    render(<AppRefreshCard />)

    await user.click(screen.getByRole('button', { name: 'Refresh app' }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Refresh app' })).toBeEnabled(),
    )
  })
})
