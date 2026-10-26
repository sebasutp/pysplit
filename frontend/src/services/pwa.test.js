import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { verifyMock, fetchContractMock, verifyIncomingMock } = vi.hoisted(() => ({
  verifyMock: vi.fn(),
  fetchContractMock: vi.fn(),
  verifyIncomingMock: vi.fn(),
}))

vi.mock('virtual:pwa-register', () => ({ registerSW: vi.fn() }))
vi.mock('./db', () => ({
  verifyDatabaseCompatibility: verifyMock,
  fetchIncomingBuildContract: fetchContractMock,
  verifyIncomingBuildCompatibility: verifyIncomingMock,
}))

import { CACHE_NAMES } from '../../pwa.config.js'
import {
  activateUpdate,
  cleanupOutdatedRuntimeCaches,
  getPwaState,
  resetPwaForTests,
  startPwa,
  subscribePwa,
} from './pwa'

/** @type {any} */
let callbacks
/** @type {any} */
let updateServiceWorker
/** @type {any} */
let emit = null
/** @type {(() => void)|null} */
let unsubscribe = null

beforeEach(() => {
  resetPwaForTests()
  verifyMock.mockReset()
  verifyMock.mockResolvedValue({ version: 3, tables: [] })
  fetchContractMock.mockReset()
  fetchContractMock.mockResolvedValue({
    schemaVersion: 3,
    requiredTables: ['outbox'],
    requiredIndexes: {},
  })
  verifyIncomingMock.mockReset()
  verifyIncomingMock.mockResolvedValue({ version: 3, incomingVersion: 3 })
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: {},
  })
  updateServiceWorker = vi.fn().mockResolvedValue(undefined)
  startPwa({
    force: true,
    register: (/** @type {any} */ options) => {
      callbacks = options
      return updateServiceWorker
    },
  })
  emit = null
  unsubscribe = subscribePwa((/** @type {any} */ state) => {
    emit = state
  })
})

describe('service worker update lifecycle', () => {
  it('registers without activating a waiting worker automatically', () => {
    expect(getPwaState().needRefresh).toBe(false)
    callbacks.onRegisteredSW('/sw.js', { scope: '/' })
    expect(getPwaState().registration).toEqual({ scope: '/' })

    expect(updateServiceWorker).not.toHaveBeenCalled()
    expect(emit.needRefresh).toBe(false)
  })

  it('shows the update prompt and activates only after the explicit action', async () => {
    callbacks.onNeedRefresh()
    expect(getPwaState().needRefresh).toBe(true)
    expect(emit.needRefresh).toBe(true)
    expect(updateServiceWorker).not.toHaveBeenCalled()

    await expect(activateUpdate()).resolves.toBe(true)
    expect(verifyMock).toHaveBeenCalledTimes(1)
    expect(fetchContractMock).toHaveBeenCalledTimes(1)
    expect(verifyIncomingMock).toHaveBeenCalledTimes(1)
    expect(updateServiceWorker).toHaveBeenCalledWith(true)
  })

  it('keeps the update waiting when the Dexie compatibility check fails', async () => {
    verifyMock.mockRejectedValueOnce(new Error('missing outbox table'))
    callbacks.onNeedRefresh()

    await expect(activateUpdate()).resolves.toBe(false)
    expect(updateServiceWorker).not.toHaveBeenCalled()
    expect(getPwaState().error).toContain('missing outbox table')
    expect(getPwaState().needRefresh).toBe(true)
  })

  it('keeps the update waiting when the incoming build contract is incompatible', async () => {
    verifyIncomingMock.mockRejectedValueOnce(new Error('Incoming build drops Dexie tables: outbox'))
    callbacks.onNeedRefresh()

    await expect(activateUpdate()).resolves.toBe(false)
    expect(updateServiceWorker).not.toHaveBeenCalled()
    expect(getPwaState().error).toContain('Incoming build drops Dexie tables: outbox')
    expect(getPwaState().needRefresh).toBe(true)
  })

  it('reports offline readiness and registration errors', () => {
    callbacks.onOfflineReady()
    expect(emit.offlineReady).toBe(true)

    callbacks.onRegisterError(new Error('blocked'))
    expect(getPwaState().error).toBe('blocked')
  })

  it('deletes old runtime cache names but keeps the current ones', async () => {
    const deleted = /** @type {string[]} */ ([])
    const names = [
      'pysplit-images-v1',
      CACHE_NAMES.images,
      'pysplit-fonts-v1',
      CACHE_NAMES.fonts,
      'workbox-precache-v2',
    ]
    vi.stubGlobal('caches', {
      keys: vi.fn().mockResolvedValue(names),
      delete: vi.fn(async (/** @type {string} */ name) => {
        deleted.push(name)
        return true
      }),
    })

    await expect(cleanupOutdatedRuntimeCaches()).resolves.toEqual([
      'pysplit-images-v1',
      'pysplit-fonts-v1',
    ])
    expect(deleted).toEqual(['pysplit-images-v1', 'pysplit-fonts-v1'])
    vi.unstubAllGlobals()
  })
})

afterEach(() => {
  unsubscribe?.()
  vi.unstubAllGlobals()
})
