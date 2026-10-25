import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useGlobalBalance } from './useGlobalBalance'

const { forUser } = vi.hoisted(() => ({ forUser: vi.fn() }))

vi.mock('../services/repository', () => ({
  repository: { balances: { forUser } },
}))

beforeEach(() => {
  localStorage.clear()
  forUser.mockReset()
})

describe('useGlobalBalance', () => {
  it('ignores a response from an aborted request', async () => {
    localStorage.setItem('g1-activeUser', 'p1')
    localStorage.setItem('g2-activeUser', 'p2')

    /** @type {(value: any) => void} */
    let resolveFirst
    forUser
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirst = resolve
          }),
      )
      .mockResolvedValueOnce([{ group_id: 'g1', amount: 10 }])

    const { result, rerender } = renderHook(({ groups }) => useGlobalBalance(groups), {
      initialProps: {
        groups: [
          { id: 'g1', name: 'One' },
          { id: 'g2', name: 'Two' },
        ],
      },
    })

    await waitFor(() => expect(forUser).toHaveBeenCalledTimes(1))
    rerender({ groups: [{ id: 'g1', name: 'One' }] })
    await waitFor(() => expect(result.current.balances).toEqual([{ group_id: 'g1', amount: 10 }]))

    await act(async () => {
      resolveFirst([{ group_id: 'g1', amount: 999 }])
    })

    expect(result.current.balances).toEqual([{ group_id: 'g1', amount: 10 }])
    expect(result.current.loading).toBe(false)
  })
})
