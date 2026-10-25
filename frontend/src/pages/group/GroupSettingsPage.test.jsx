import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import '../../services/i18n'
import { GroupSettingsPage } from './GroupSettingsPage'

const { reloadGroup, update } = vi.hoisted(() => ({
  reloadGroup: vi.fn(),
  update: vi.fn(),
}))

vi.mock('../../components/groups/GroupLayout', () => ({
  useGroupContext: () => ({
    group: {
      id: 'group-1',
      name: 'Trip',
      currency: '$',
      currency_code: 'USD',
      participants: [{ id: 'p1', name: 'Alice' }],
    },
    details: { participants_with_expenses: ['p1'] },
    reloadGroup,
  }),
}))

vi.mock('../../components/groups/GroupForm', () => ({
  GroupForm: (/** @type {any} */ props) => (
    <div>
      <span data-testid="locked-participants">{props.lockedParticipantIds.join(',')}</span>
      <button
        type="button"
        onClick={() =>
          void props.onSubmit({
            name: 'Trip updated',
            information: '',
            currency: '$',
            currencyCode: 'USD',
            participants: [{ id: 'p1', name: 'Alice' }],
          })
        }
      >
        Save
      </button>
    </div>
  ),
}))

vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({ toast: vi.fn(), dismiss: vi.fn() }),
}))

vi.mock('../../services/repository', () => ({
  repository: { groups: { update } },
}))

beforeEach(() => {
  reloadGroup.mockReset().mockResolvedValue(undefined)
  update.mockReset().mockResolvedValue({ id: 'group-1' })
})

describe('GroupSettingsPage', () => {
  it('refreshes the shared group/details once on mount and after save', async () => {
    render(<GroupSettingsPage />)

    expect(reloadGroup).toHaveBeenCalledTimes(1)
    expect(screen.getByTestId('locked-participants')).toHaveTextContent('p1')

    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(update).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(reloadGroup).toHaveBeenCalledTimes(2))
  })
})
