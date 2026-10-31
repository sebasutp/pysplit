import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  activateUpdate: vi.fn(),
  subscribePwa: vi.fn(),
  pwaSupported: vi.fn(() => true),
  listener: /** @type {any} */ (null),
}))

vi.mock('../services/pwa', () => ({
  activateUpdate: mocks.activateUpdate,
  pwaSupported: mocks.pwaSupported,
  subscribePwa: (/** @type {any} */ listener) => {
    mocks.listener = listener
    listener({
      needRefresh: false,
      offlineReady: false,
      error: null,
      registration: null,
      updateServiceWorker: null,
    })
    return () => {
      mocks.listener = null
    }
  },
}))

import { usePwa } from './usePwa'

beforeEach(() => {
  mocks.activateUpdate.mockReset()
  mocks.activateUpdate.mockResolvedValue(true)
  mocks.listener = null
})

describe('usePwa', () => {
  it('captures the install prompt and clears it after the user chooses', async () => {
    const { result } = renderHook(() => usePwa())
    expect(result.current.canInstall).toBe(false)

    const prompt = vi.fn().mockResolvedValue(undefined)
    const event = new Event('beforeinstallprompt')
    Object.assign(event, {
      prompt,
      userChoice: Promise.resolve({ outcome: 'accepted' }),
    })
    act(() => {
      window.dispatchEvent(event)
    })

    await waitFor(() => expect(result.current.canInstall).toBe(true))
    await act(async () => {
      await expect(result.current.promptInstall()).resolves.toBe(true)
    })
    expect(prompt).toHaveBeenCalledTimes(1)
    expect(result.current.canInstall).toBe(false)
  })

  it('exposes update state and forwards the explicit reload action', async () => {
    const { result } = renderHook(() => usePwa())
    act(() => {
      mocks.listener({
        needRefresh: true,
        offlineReady: true,
        error: null,
        registration: null,
        updateServiceWorker: null,
      })
    })

    await waitFor(() => expect(result.current.needRefresh).toBe(true))
    expect(result.current.offlineReady).toBe(true)
    await act(async () => {
      await result.current.applyUpdate()
    })
    expect(mocks.activateUpdate).toHaveBeenCalledTimes(1)
  })
})
