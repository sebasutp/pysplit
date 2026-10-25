import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useExpenses } from './useExpenses'

const { list } = vi.hoisted(() => ({ list: vi.fn() }))

vi.mock('../services/repository', () => ({
  repository: { expenses: { list } },
}))

/** @param {number} start @param {number} count */
function page(start, count) {
  return Array.from({ length: count }, (_, index) => ({
    id: `e${start + index}`,
    title: `Expense ${start + index}`,
  }))
}

beforeEach(() => {
  list.mockReset()
})

describe('useExpenses', () => {
  it('appends page two, keeps filters and reaches expenses beyond 100', async () => {
    list.mockImplementation((_groupId, options) => {
      if (options.offset === 0) return Promise.resolve({ items: page(0, 100), total: 150 })
      return Promise.resolve({ items: page(100, 50), total: 150 })
    })

    const { result } = renderHook(() =>
      useExpenses('group-1', { q: 'dinner', from: '2024-01-01', to: '2024-12-31' }),
    )

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.items).toHaveLength(100)
    expect(result.current.hasMore).toBe(true)

    await act(async () => {
      await result.current.loadMore()
    })

    expect(result.current.items).toHaveLength(150)
    expect(result.current.items.at(-1).id).toBe('e149')
    expect(result.current.hasMore).toBe(false)
    expect(list).toHaveBeenCalledTimes(2)
    expect(list.mock.calls[1][1]).toMatchObject({
      q: 'dinner',
      from: '2024-01-01',
      to: '2024-12-31',
      limit: 100,
      offset: 100,
    })
  })

  it('ignores duplicate rows and concurrent load-more calls', async () => {
    /** @type {(value: any) => void} */
    let resolveSecond
    list.mockImplementation((_groupId, options) => {
      if (options.offset === 0) return Promise.resolve({ items: page(0, 2), total: 5 })
      return new Promise((resolve) => {
        resolveSecond = resolve
      })
    })

    const { result } = renderHook(() => useExpenses('group-1'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    /** @type {Promise<void>|undefined} */
    let first
    act(() => {
      first = result.current.loadMore()
      void result.current.loadMore()
    })
    expect(list).toHaveBeenCalledTimes(2)

    await act(async () => {
      resolveSecond({ items: [...page(0, 2), ...page(2, 2)], total: 5 })
      await first
    })

    expect(result.current.items.map((item) => item.id)).toEqual(['e0', 'e1', 'e2', 'e3'])
    expect(result.current.hasMore).toBe(true)
  })

  it('does not append a stale page after the filters change', async () => {
    /** @type {(value: any) => void} */
    let resolveStalePage
    list.mockImplementation((_groupId, options) => {
      if (options.offset === 0) {
        if (options.q === 'old') return Promise.resolve({ items: page(0, 100), total: 110 })
        return Promise.resolve({ items: page(0, 1), total: 1 })
      }
      return new Promise((resolve) => {
        resolveStalePage = resolve
      })
    })

    const { result, rerender } = renderHook(
      ({ q }) => useExpenses('group-1', { q }),
      { initialProps: { q: 'old' } },
    )
    await waitFor(() => expect(result.current.items).toHaveLength(100))

    /** @type {Promise<void>|undefined} */
    let staleLoad
    act(() => {
      staleLoad = result.current.loadMore()
    })

    rerender({ q: 'new' })
    await waitFor(() => expect(result.current.items).toHaveLength(1))

    await act(async () => {
      resolveStalePage({ items: page(100, 10), total: 110 })
      await staleLoad
    })
    expect(result.current.items).toHaveLength(1)
    expect(result.current.items[0].id).toBe('e0')
  })
})
