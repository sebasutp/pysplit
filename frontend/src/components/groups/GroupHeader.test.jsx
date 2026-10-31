import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import '../../services/i18n'
import { GroupHeader } from './GroupHeader'

const group = {
  id: 'group-1',
  name: 'Trip',
  information: 'Meet at the station',
}

/** @param {Record<string, unknown>} overrides */
function renderHeader(overrides = {}) {
  return render(
    <MemoryRouter>
      <GroupHeader group={{ ...group, ...overrides }} />
    </MemoryRouter>,
  )
}

describe('GroupHeader', () => {
  it('shows the Information tab when the group has information', () => {
    renderHeader()

    expect(screen.getByRole('tab', { name: 'Information' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Settings' })).toBeInTheDocument()
  })

  it.each([null, '', '   \n\t '])('hides Information when it is empty (%j)', (information) => {
    renderHeader({ information })

    expect(screen.queryByRole('tab', { name: 'Information' })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Settings' })).toBeInTheDocument()
  })
})
