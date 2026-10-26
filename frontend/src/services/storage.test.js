import { afterEach, describe, expect, it, vi } from 'vitest'

import { formatBytes, quotaLevel, readStorageStatus } from './storage'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('storage quota', () => {
  it('classifies usage thresholds', () => {
    expect(quotaLevel(10, 100)).toBe('ok')
    expect(quotaLevel(75, 100)).toBe('warning')
    expect(quotaLevel(90, 100)).toBe('critical')
    expect(quotaLevel(1, 0)).toBe('unknown')
    expect(quotaLevel(null, null)).toBe('unknown')
  })

  it('formats byte counts', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1024)).toBe('1 KB')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5 MB')
  })

  it('reads persisted state and estimate, requesting persistence only when asked', async () => {
    const persisted = vi.fn().mockResolvedValue(false)
    const persist = vi.fn().mockResolvedValue(true)
    const estimate = vi.fn().mockResolvedValue({ usage: 950, quota: 1000 })
    Object.defineProperty(navigator, 'storage', {
      configurable: true,
      value: { persisted, persist, estimate },
    })

    const first = await readStorageStatus()
    expect(first).toMatchObject({
      supported: true,
      persisted: false,
      usage: 950,
      quota: 1000,
      level: 'critical',
    })
    expect(persist).not.toHaveBeenCalled()

    const second = await readStorageStatus({ persist: true })
    expect(second.persisted).toBe(true)
    expect(persist).toHaveBeenCalledTimes(1)
  })
})
