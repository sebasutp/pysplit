import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { GroupForm } from './GroupForm'

const initial = {
  id: 'group-1',
  name: 'Old trip',
  information: 'Old information',
  currency: '$',
  currency_code: 'USD',
  participants: [
    { id: 'p1', name: 'Alice' },
    { id: 'p2', name: 'Bob' },
  ],
}

function renderForm(props = {}) {
  return render(
    <MemoryRouter>
      <GroupForm initial={initial} onSubmit={vi.fn()} {...props} />
    </MemoryRouter>,
  )
}

describe('GroupForm', () => {
  it('applies fresher initial values when the group details change', async () => {
    const { rerender } = renderForm()

    expect(screen.getByLabelText('Group name')).toHaveValue('Old trip')
    expect(screen.getByLabelText('Participant #1')).toHaveValue('Alice')

    const fresh = {
      id: 'group-1',
      name: 'Fresh trip',
      information: 'Fresh information',
      currency: '€',
      currency_code: 'EUR',
      participants: [
        { id: 'p1', name: 'Alice' },
        { id: 'p2', name: 'Bob' },
        { id: 'p3', name: 'Carol' },
      ],
    }

    rerender(
      <MemoryRouter>
        <GroupForm initial={fresh} onSubmit={vi.fn()} />
      </MemoryRouter>,
    )

    await waitFor(() => expect(screen.getByLabelText('Group name')).toHaveValue('Fresh trip'))
    expect(screen.getByLabelText('Group information')).toHaveValue('Fresh information')
    expect(screen.getByLabelText('Main currency')).toHaveValue('EUR')
    // The shared currency helper supplies the symbol for a code-only group.
    expect(screen.getByLabelText('Currency symbol')).toHaveValue('€')
    expect(screen.getByLabelText('Participant #3')).toHaveValue('Carol')
  })

  it('does not reset in-progress edits when a parent re-renders with the same data', async () => {
    const user = userEvent.setup()
    const { rerender } = renderForm()

    const name = screen.getByLabelText('Group name')
    await user.clear(name)
    await user.type(name, 'My edited trip')

    // GroupSettingsPage passes a new object on every render; an identical
    // fingerprint must not clobber the user's edits.
    rerender(
      <MemoryRouter>
        <GroupForm
          initial={{ ...initial, participants: initial.participants.map((item) => ({ ...item })) }}
          onSubmit={vi.fn()}
        />
      </MemoryRouter>,
    )

    expect(screen.getByLabelText('Group name')).toHaveValue('My edited trip')
  })
})
