import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import '../services/i18n'
import { AdminPage } from './AdminPage'

const { metrics, usersList, groupsList } = vi.hoisted(() => ({
  metrics: vi.fn(),
  usersList: vi.fn(),
  groupsList: vi.fn(),
}))

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'admin', tier: 'admin' },
    loading: false,
    isAdmin: true,
  }),
}))

vi.mock('../hooks/useToast', () => ({
  useToast: () => ({ toast: vi.fn(), dismiss: vi.fn() }),
}))

vi.mock('../services/repository', () => ({
  repository: {
    admin: {
      metrics,
      users: {
        list: usersList,
        setTier: vi.fn(),
        remove: vi.fn(),
        preauthorize: vi.fn(),
      },
      groups: { list: groupsList, remove: vi.fn() },
    },
  },
}))

/** @param {number} start @param {number} count */
function users(start, count) {
  return Array.from({ length: count }, (_, index) => ({
    id: `u${start + index}`,
    name: `User ${start + index}`,
    email: `user${start + index}@example.com`,
    groups_count: 1,
    tier: 'sync_users',
  }))
}

/** @param {number} start @param {number} count */
function groups(start, count) {
  return Array.from({ length: count }, (_, index) => ({
    id: `g${start + index}`,
    name: `Group ${start + index}`,
    participants_count: 2,
    expenses_count: 3,
  }))
}

beforeEach(() => {
  metrics.mockReset().mockResolvedValue({
    total_groups: 25,
    total_expenses: 3,
    total_users: 25,
  })
  usersList.mockReset().mockImplementation((input) => {
    const offset = input.offset || 0
    return Promise.resolve({ items: users(offset, offset ? 5 : 20), total: 25, offset })
  })
  groupsList.mockReset().mockResolvedValue({ items: [], total: 0 })
})

describe('AdminPage pagination', () => {
  it('can reach users and groups beyond the first 20', async () => {
    groupsList.mockImplementation((input) => {
      const offset = input.offset || 0
      return Promise.resolve({ items: groups(offset, offset ? 5 : 20), total: 25, offset })
    })

    render(
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText('User 0')).toBeInTheDocument()
    expect(screen.getByText('Group 0')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Load more users' }))
    expect(await screen.findByText('User 24')).toBeInTheDocument()
    expect(usersList.mock.calls.at(-1)?.[0]).toMatchObject({ limit: 20, offset: 20 })

    fireEvent.click(screen.getByRole('button', { name: 'Load more groups' }))
    expect(await screen.findByText('Group 24')).toBeInTheDocument()
    expect(groupsList.mock.calls.at(-1)?.[0]).toMatchObject({ limit: 20, offset: 20 })
  })

  it('does not refetch metrics while searching', async () => {
    render(
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>,
    )

    await screen.findByText('User 0')
    expect(metrics).toHaveBeenCalledTimes(1)

    fireEvent.change(screen.getByLabelText('Search users'), { target: { value: 'ali' } })

    await waitFor(
      () => {
        expect(usersList.mock.calls.at(-1)?.[0]).toMatchObject({ q: 'ali' })
      },
      { timeout: 2000 },
    )
    expect(metrics).toHaveBeenCalledTimes(1)
  })
})
