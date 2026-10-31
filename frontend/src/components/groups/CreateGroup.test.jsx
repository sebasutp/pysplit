import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import '../../services/i18n'
import { CreateGroup } from './GroupForm'

const { create } = vi.hoisted(() => ({ create: vi.fn() }))

vi.mock('../../services/repository', () => ({
  repository: { groups: { create } },
}))

beforeEach(() => {
  localStorage.clear()
  create.mockReset()
  create.mockResolvedValue({ id: 'group-1', name: 'Trip' })
})

describe('CreateGroup', () => {
  it('leaves the active-user choice unanswered for the first-visit dialog', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/groups/create']}>
        <Routes>
          <Route path="/groups/create" element={<CreateGroup />} />
          <Route path="/groups/:groupId" element={<div />} />
        </Routes>
      </MemoryRouter>,
    )

    await user.type(screen.getByLabelText('Group name'), 'Trip')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1))
    expect(localStorage.getItem('group-1-activeUser')).toBeNull()
  })
})
