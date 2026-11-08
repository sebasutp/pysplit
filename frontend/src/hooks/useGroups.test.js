import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { sync } = vi.hoisted(() => ({ sync: vi.fn() }))

vi.mock('../services/repository', () => ({
  repository: { groups: { sync } },
}))

import { useGroups } from './useGroups'

beforeEach(() => {
  localStorage.clear()
  sync.mockReset()
})

describe('useGroups', () => {
  it('renders cached recent groups immediately while the sync is pending', () => {
    localStorage.setItem(
      'recentGroups',
      JSON.stringify([{ id: 'g1', name: 'Cached group' }]),
    )
    localStorage.setItem('starredGroups', JSON.stringify(['g1']))
    sync.mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useGroups())

    expect(result.current.status).toBe('complete')
    expect(result.current.groups).toEqual([{ id: 'g1', name: 'Cached group' }])
    expect(result.current.starredGroups).toEqual(['g1'])
  })

  it('stays in the loading state when there is no cached group to show', () => {
    sync.mockReturnValue(new Promise(() => {}))

    const { result } = renderHook(() => useGroups())

    expect(result.current.status).toBe('pending')
    expect(result.current.groups).toEqual([])
  })
})
