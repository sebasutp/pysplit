import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useActivities } from './useActivities'

const { list } = vi.hoisted(() => ({ list: vi.fn() }))

vi.mock('../services/repository', () => ({
  repository: { activities: { list } },
}))

beforeEach(() => {
  list.mockReset()
})

describe('useActivities', () => {
  it('guards concurrent load-more calls and deduplicates rows', async () => {
    list.mockResolvedValueOnce({
      items: [{ id: 'a1' }],
      next_cursor: '1',
      has_more: true,
    })
    /** @type {(value: any) => void} */
    let resolvePage
    list.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolvePage = resolve
        }),
    )

    const { result } = renderHook(() => useActivities('group-1'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    /** @type {Promise<void>|undefined} */
    let first
    act(() => {
      first = result.current.loadMore()
      void result.current.loadMore()
    })
    expect(list).toHaveBeenCalledTimes(2)

    await act(async () => {
      resolvePage({
        items: [{ id: 'a1' }, { id: 'a2' }],
        next_cursor: '2',
        has_more: true,
      })
      await first
    })

    expect(result.current.items.map((item) => item.id)).toEqual(['a1', 'a2'])
  })

  it('captures load-more failures instead of rejecting', async () => {
    list.mockResolvedValueOnce({
      items: [{ id: 'a1' }],
      next_cursor: '1',
      has_more: true,
    })
    list.mockRejectedValueOnce(Object.assign(new Error('offline'), { code: 'network' }))

    const { result } = renderHook(() => useActivities('group-1'))
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.loadMore()
    })

    expect(result.current.error).toBeTruthy()
    expect(result.current.loadingMore).toBe(false)
  })

  it('does not append a stale page after switching groups', async () => {
    /** @type {(value: any) => void} */
    let resolveGroupA
    list.mockImplementation((id, options) => {
      if (id === 'group-b') {
        return Promise.resolve({
          items: [{ id: 'b1' }],
          next_cursor: null,
          has_more: false,
        })
      }
      if (options.cursor) {
        return new Promise((resolve) => {
          resolveGroupA = resolve
        })
      }
      return Promise.resolve({
        items: [{ id: 'a1' }],
        next_cursor: '1',
        has_more: true,
      })
    })

    const { result, rerender } = renderHook(({ id }) => useActivities(id), {
      initialProps: { id: 'group-a' },
    })
    await waitFor(() => expect(result.current.items).toEqual([{ id: 'a1' }]))

    /** @type {Promise<void>|undefined} */
    let pending
    act(() => {
      pending = result.current.loadMore()
    })
    expect(list).toHaveBeenCalledTimes(2)

    rerender({ id: 'group-b' })
    await waitFor(() => expect(result.current.items).toEqual([{ id: 'b1' }]))
    expect(result.current.loadingMore).toBe(false)

    await act(async () => {
      resolveGroupA({ items: [{ id: 'a2' }], next_cursor: '2', has_more: true })
      await pending
    })

    expect(result.current.items).toEqual([{ id: 'b1' }])
    expect(result.current.hasMore).toBe(false)
    expect(result.current.loadingMore).toBe(false)
  })
})
