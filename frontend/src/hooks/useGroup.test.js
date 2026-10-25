import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useGroup } from './useGroup'

const { get, details } = vi.hoisted(() => ({ get: vi.fn(), details: vi.fn() }))

vi.mock('../services/repository', () => ({
  repository: { groups: { get, details } },
}))

/** @returns {{promise: Promise<any>, resolve: (value: any) => void}} */
function deferred() {
  /** @type {(value: any) => void} */
  let resolve = () => {}
  const promise = new Promise((res) => {
    resolve = res
  })
  return { promise, resolve }
}

beforeEach(() => {
  get.mockReset()
  details.mockReset()
})

describe('useGroup', () => {
  it('clears the previous group as soon as the id changes', async () => {
    const pending = new Map()
    get.mockImplementation((id) => {
      if (!pending.has(id)) pending.set(id, { get: deferred(), details: deferred() })
      return pending.get(id).get.promise
    })
    details.mockImplementation((id) => {
      if (!pending.has(id)) pending.set(id, { get: deferred(), details: deferred() })
      return pending.get(id).details.promise
    })

    const { result, rerender } = renderHook(({ id }) => useGroup(id), {
      initialProps: { id: 'group-a' },
    })

    act(() => {
      pending.get('group-a').get.resolve({ id: 'group-a', name: 'A' })
      pending.get('group-a').details.resolve({ id: 'group-a' })
    })
    await act(async () => {})
    expect(result.current.group).toEqual({ id: 'group-a', name: 'A' })

    rerender({ id: 'group-b' })

    // The previous group must not be visible under the new URL.
    expect(result.current.group).toBeNull()
    expect(result.current.details).toBeNull()
    expect(result.current.loading).toBe(true)

    act(() => {
      pending.get('group-b').get.resolve({ id: 'group-b', name: 'B' })
      pending.get('group-b').details.resolve({ id: 'group-b' })
    })
    await act(async () => {})
    expect(result.current.group).toEqual({ id: 'group-b', name: 'B' })
    expect(result.current.loading).toBe(false)
  })

  it('keeps the current group visible while reloading the same id', async () => {
    /** @type {((value: any) => void)[]} */
    const getQueue = []
    /** @type {((value: any) => void)[]} */
    const detailsQueue = []
    get.mockImplementation(
      () =>
        new Promise((resolve) => {
          getQueue.push(resolve)
        }),
    )
    details.mockImplementation(
      () =>
        new Promise((resolve) => {
          detailsQueue.push(resolve)
        }),
    )

    const { result } = renderHook(() => useGroup('group-a'))
    act(() => {
      getQueue[0]({ id: 'group-a', name: 'A' })
      detailsQueue[0]({ id: 'group-a' })
    })
    await act(async () => {})
    expect(result.current.group).toEqual({ id: 'group-a', name: 'A' })

    act(() => {
      void result.current.reload()
    })

    expect(getQueue).toHaveLength(2)
    expect(result.current.group).toEqual({ id: 'group-a', name: 'A' })
    expect(result.current.details).toEqual({ id: 'group-a' })
    expect(result.current.loading).toBe(true)

    act(() => {
      getQueue[1]({ id: 'group-a', name: 'A updated' })
      detailsQueue[1]({ id: 'group-a', participants_with_expenses: ['p1'] })
    })
    await act(async () => {})

    expect(result.current.group).toEqual({ id: 'group-a', name: 'A updated' })
    expect(result.current.details).toEqual({
      id: 'group-a',
      participants_with_expenses: ['p1'],
    })
    expect(result.current.loading).toBe(false)
  })
})
