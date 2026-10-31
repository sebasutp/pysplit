import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import '../../services/i18n'
import { GroupLayout } from './GroupLayout'

const { group, auth } = vi.hoisted(() => ({
  group: {
    id: 'group-1',
    name: 'Trip',
    information: null,
    participants: [
      { id: 'p1', name: 'Alice' },
      { id: 'p2', name: 'Bob' },
    ],
  },
  auth: { user: { id: 'user-1', name: '  alice  ' } },
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => auth,
}))

vi.mock('../../hooks/useGroup', () => ({
  useGroup: () => ({
    group,
    details: null,
    loading: false,
    error: null,
    reload: vi.fn(),
  }),
}))

vi.mock('../../services/repository', () => ({
  repository: { groups: { recordAccess: vi.fn().mockResolvedValue(undefined) } },
}))

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/groups/group-1']}>
      <Routes>
        <Route path="/groups/:groupId" element={<GroupLayout />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  localStorage.clear()
})

describe('GroupLayout active user', () => {
  it('preselects, but still shows, the participant matching the account name', async () => {
    renderLayout()

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Alice' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Bob' })).not.toBeChecked()
  })

  it('does not reopen the dialog after an explicit "nobody" choice', async () => {
    localStorage.setItem('group-1-activeUser', 'None')
    renderLayout()

    await screen.findByText('Trip')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
