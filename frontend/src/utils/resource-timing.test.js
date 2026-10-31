import { afterEach, describe, expect, it, vi } from 'vitest'

import { stabilizeResourceTiming } from './resource-timing'

const original = performance.getEntriesByType

afterEach(() => {
  Object.defineProperty(performance, 'getEntriesByType', {
    configurable: true,
    writable: true,
    value: original,
  })
  vi.restoreAllMocks()
})

describe('stabilizeResourceTiming', () => {
  it('drops incomplete resource entries without touching other entry types', () => {
    const entries = [
      { name: 'complete.js', startTime: 1 },
      undefined,
      { name: 'incomplete.png' },
    ]
    const spy = vi.fn((type) => (type === 'resource' ? entries : [{ name: 'mark', startTime: 0 }]))
    Object.defineProperty(performance, 'getEntriesByType', {
      configurable: true,
      writable: true,
      value: spy,
    })

    stabilizeResourceTiming()

    expect(performance.getEntriesByType('resource')).toEqual([
      { name: 'complete.js', startTime: 1 },
    ])
    expect(performance.getEntriesByType('mark')).toEqual([{ name: 'mark', startTime: 0 }])
  })
})
