import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useDrilldown } from './useStats'

const { monthExpenses, categoryExpenses } = vi.hoisted(() => ({
  monthExpenses: vi.fn(),
  categoryExpenses: vi.fn(),
}))

vi.mock('../services/repository', () => ({
  repository: { stats: { monthExpenses, categoryExpenses } },
}))

beforeEach(() => {
  monthExpenses.mockReset()
  categoryExpenses.mockReset()
})

describe('useDrilldown', () => {
  it('stays idle when no target is selected', async () => {
    const { result, rerender } = renderHook(
      ({ target }) => useDrilldown('group-1', target),
      { initialProps: { target: /** @type {any} */ (null) } },
    )

    expect(monthExpenses).not.toHaveBeenCalled()
    expect(categoryExpenses).not.toHaveBeenCalled()
    expect(result.current.loading).toBe(false)
    expect(result.current.expenses).toEqual([])

    monthExpenses.mockResolvedValue({ expenses: [{ id: 'e1' }] })
    rerender({ target: { kind: 'month', month: '2024-01' } })
    await waitFor(() => expect(result.current.expenses).toHaveLength(1))
    expect(monthExpenses).toHaveBeenCalledTimes(1)
    expect(monthExpenses.mock.calls[0][1]).toBe('2024-01')
  })

  it('clears the previous selection immediately and skips the dummy period', async () => {
    monthExpenses.mockResolvedValue({ expenses: [{ id: 'e1' }] })

    const { result, rerender } = renderHook(
      ({ target }) => useDrilldown('group-1', target),
      { initialProps: { target: /** @type {any} */ ({ kind: 'month', month: '2024-01' }) } },
    )
    await waitFor(() => expect(result.current.expenses).toHaveLength(1))

    /** @type {(value: any) => void} */
    let resolveNext
    monthExpenses.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveNext = resolve
        }),
    )

    rerender({ target: { kind: 'month', month: '2024-02' } })
    expect(result.current.expenses).toEqual([])

    await act(async () => {
      resolveNext({ expenses: [{ id: 'e2' }] })
    })
    expect(result.current.expenses).toEqual([{ id: 'e2' }])

    monthExpenses.mockClear()
    rerender({ target: null })
    expect(result.current.expenses).toEqual([])
    expect(monthExpenses).not.toHaveBeenCalled()
  })
})
