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
  forceRefreshApp,
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
/** @type {Set<(event: Event) => void>} */
let controllerChangeListeners = new Set()
/** @type {any} */
let reloadMock
/** @type {any} */
let replaceMock

function emitControllerChange() {
  for (const listener of Array.from(controllerChangeListeners)) {
    listener(new Event('controllerchange'))
  }
}

beforeEach(() => {
  resetPwaForTests()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
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
  controllerChangeListeners = new Set()
  Object.defineProperty(navigator, 'serviceWorker', {
    configurable: true,
    value: {
      addEventListener: vi.fn(
        (/** @type {string} */ type, /** @type {(event: Event) => void} */ listener) => {
          if (type === 'controllerchange') controllerChangeListeners.add(listener)
        },
      ),
      removeEventListener: vi.fn(
        (/** @type {string} */ type, /** @type {(event: Event) => void} */ listener) => {
          if (type === 'controllerchange') controllerChangeListeners.delete(listener)
        },
      ),
    },
  })
  reloadMock = vi.fn()
  replaceMock = vi.fn()
  vi.stubGlobal('location', {
    href: 'http://localhost/groups',
    reload: reloadMock,
    replace: replaceMock,
  })
  updateServiceWorker = vi.fn(async () => {
    emitControllerChange()
  })
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
  it('removes a stale service worker in development instead of registering', async () => {
    resetPwaForTests()
    const unregister = vi.fn().mockResolvedValue(true)
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: { getRegistrations: vi.fn().mockResolvedValue([{ unregister }]) },
    })
    const deleteCache = vi.fn().mockResolvedValue(true)
    vi.stubGlobal('caches', {
      keys: vi.fn().mockResolvedValue(['old-build']),
      delete: deleteCache,
    })
    const register = vi.fn()

    startPwa({ register })

    await vi.waitFor(() => expect(unregister).toHaveBeenCalledTimes(1))
    expect(deleteCache).toHaveBeenCalledWith('old-build')
    expect(register).not.toHaveBeenCalled()
    vi.unstubAllGlobals()
  })

  it('registers without activating a waiting worker automatically', () => {
    expect(getPwaState().needRefresh).toBe(false)
    callbacks.onRegisteredSW('/sw.js', { scope: '/' })
    expect(getPwaState().registration).toEqual({ scope: '/' })

    expect(updateServiceWorker).not.toHaveBeenCalled()
    expect(emit.needRefresh).toBe(false)
  })

  it('auto-activates an online update after compatibility checks', async () => {
    callbacks.onNeedRefresh()
    expect(getPwaState().needRefresh).toBe(true)
    expect(emit.needRefresh).toBe(true)

    await vi.waitFor(() => expect(updateServiceWorker).toHaveBeenCalledWith(false))
    await vi.waitFor(() => expect(reloadMock).toHaveBeenCalled())
    expect(verifyMock).toHaveBeenCalledTimes(1)
    expect(fetchContractMock).toHaveBeenCalledTimes(1)
    expect(verifyIncomingMock).toHaveBeenCalledTimes(1)
  })

  it('waits for controllerchange before reloading', async () => {
    /** @type {any} */
    let finish = null
    updateServiceWorker.mockImplementation(async () => {
      finish = () => emitControllerChange()
    })
    callbacks.onNeedRefresh()

    await vi.waitFor(() => expect(updateServiceWorker).toHaveBeenCalledWith(false))
    expect(reloadMock).not.toHaveBeenCalled()

    finish?.()
    await vi.waitFor(() => expect(reloadMock).toHaveBeenCalled())
  })

  it('waits offline and auto-activates when the browser comes online', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    callbacks.onNeedRefresh()
    await Promise.resolve()
    await Promise.resolve()

    expect(updateServiceWorker).not.toHaveBeenCalled()
    expect(getPwaState().needRefresh).toBe(true)

    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    window.dispatchEvent(new Event('online'))

    await vi.waitFor(() => expect(updateServiceWorker).toHaveBeenCalledWith(false))
    await vi.waitFor(() => expect(reloadMock).toHaveBeenCalled())
  })

  it('does not auto-activate offline and retries when online', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    callbacks.onNeedRefresh()
    await Promise.resolve()
    await Promise.resolve()
    expect(updateServiceWorker).not.toHaveBeenCalled()

    // Manual activation offline can fail while fetching the build contract.
    fetchContractMock.mockRejectedValueOnce(new Error('offline'))
    await expect(activateUpdate()).resolves.toBe(false)
    expect(getPwaState().error).toContain('offline')

    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    window.dispatchEvent(new Event('online'))

    await vi.waitFor(() => expect(updateServiceWorker).toHaveBeenCalledWith(false))
    await vi.waitFor(() => expect(reloadMock).toHaveBeenCalled())
  })

  it('reports updater failures and does not retry in a loop', async () => {
    updateServiceWorker.mockRejectedValueOnce(new Error('skip failed'))
    callbacks.onNeedRefresh()

    await vi.waitFor(() => expect(getPwaState().error).toContain('skip failed'))
    expect(updateServiceWorker).toHaveBeenCalledTimes(1)
    expect(reloadMock).not.toHaveBeenCalled()
    expect(getPwaState().needRefresh).toBe(true)

    window.dispatchEvent(new Event('online'))
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(updateServiceWorker).toHaveBeenCalledTimes(1)
  })

  it('keeps the prompt when the new worker never takes control', async () => {
    vi.useFakeTimers()
    try {
      updateServiceWorker.mockImplementation(async () => {})
      callbacks.onNeedRefresh()
      await vi.advanceTimersByTimeAsync(5000)

      expect(getPwaState().error).toContain('did not activate')
      expect(reloadMock).not.toHaveBeenCalled()
      expect(getPwaState().needRefresh).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it('falls back to posting SKIP_WAITING when no updater function is available', async () => {
    resetPwaForTests()
    unsubscribe?.()
    unsubscribe = null
    /** @type {any} */
    let fallbackCallbacks
    startPwa({
      force: true,
      register: (/** @type {any} */ options) => {
        fallbackCallbacks = options
        return undefined
      },
    })
    const postMessage = vi.fn(() => emitControllerChange())
    fallbackCallbacks.onRegisteredSW('/sw.js', {
      scope: '/',
      update: vi.fn(),
      waiting: { postMessage },
    })
    fallbackCallbacks.onNeedRefresh()

    await vi.waitFor(() =>
      expect(postMessage).toHaveBeenCalledWith({ type: 'SKIP_WAITING' }),
    )
    await vi.waitFor(() => expect(reloadMock).toHaveBeenCalled())
  })

  it('keeps the update waiting when the Dexie compatibility check fails', async () => {
    verifyMock.mockRejectedValueOnce(new Error('missing outbox table'))
    callbacks.onNeedRefresh()

    await vi.waitFor(() =>
      expect(getPwaState().error).toContain('missing outbox table'),
    )
    expect(updateServiceWorker).not.toHaveBeenCalled()
    expect(getPwaState().needRefresh).toBe(true)
  })

  it('keeps the update waiting when the incoming build contract is incompatible', async () => {
    verifyIncomingMock.mockRejectedValueOnce(new Error('Incoming build drops Dexie tables: outbox'))
    callbacks.onNeedRefresh()

    await vi.waitFor(() =>
      expect(getPwaState().error).toContain('Incoming build drops Dexie tables: outbox'),
    )
    expect(updateServiceWorker).not.toHaveBeenCalled()
    expect(getPwaState().needRefresh).toBe(true)
  })

  it('checks the registration on focus and online', async () => {
    const update = vi.fn().mockResolvedValue(undefined)
    callbacks.onRegisteredSW('/sw.js', { scope: '/', update })

    update.mockClear()
    window.dispatchEvent(new Event('focus'))
    await vi.waitFor(() => expect(update).toHaveBeenCalledTimes(1))

    update.mockClear()
    window.dispatchEvent(new Event('online'))
    await vi.waitFor(() => expect(update).toHaveBeenCalledTimes(1))
  })

  it('polls the registration while online', async () => {
    vi.useFakeTimers()
    try {
      const update = vi.fn().mockResolvedValue(undefined)
      callbacks.onRegisteredSW('/sw.js', { scope: '/', update })
      update.mockClear()

      await vi.advanceTimersByTimeAsync(15 * 60 * 1000)

      expect(update).toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('reports offline readiness and registration errors', () => {
    callbacks.onOfflineReady()
    expect(emit.offlineReady).toBe(true)

    callbacks.onRegisterError(new Error('blocked'))
    expect(getPwaState().error).toBe('blocked')
  })

  it('forceRefreshApp unregisters workers, clears caches and reloads with a token', async () => {
    const unregister = vi.fn().mockResolvedValue(true)
    const getRegistrations = vi.fn().mockResolvedValue([{ unregister }])
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: { getRegistrations },
    })
    const deleteCache = vi.fn().mockResolvedValue(true)
    vi.stubGlobal('caches', {
      keys: vi.fn().mockResolvedValue(['build-a', 'build-b']),
      delete: deleteCache,
    })
    const clearStorage = vi.fn()
    const deleteDatabase = vi.fn()
    vi.spyOn(Storage.prototype, 'clear').mockImplementation(clearStorage)
    vi.spyOn(indexedDB, 'deleteDatabase').mockImplementation(deleteDatabase)

    await forceRefreshApp()

    expect(getRegistrations).toHaveBeenCalledTimes(1)
    expect(unregister).toHaveBeenCalledTimes(1)
    expect(deleteCache).toHaveBeenCalledWith('build-a')
    expect(deleteCache).toHaveBeenCalledWith('build-b')
    expect(replaceMock).toHaveBeenCalledTimes(1)
    expect(String(replaceMock.mock.calls[0][0])).toContain('_refresh=')
    expect(clearStorage).not.toHaveBeenCalled()
    expect(deleteDatabase).not.toHaveBeenCalled()
  })

  it('forceRefreshApp leaves workers and caches alone while offline', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    const getRegistrations = vi.fn().mockResolvedValue([])
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: { getRegistrations },
    })
    const keys = vi.fn().mockResolvedValue(['build-a'])
    const deleteCache = vi.fn()
    vi.stubGlobal('caches', { keys, delete: deleteCache })

    await forceRefreshApp()

    expect(getRegistrations).not.toHaveBeenCalled()
    expect(keys).not.toHaveBeenCalled()
    expect(deleteCache).not.toHaveBeenCalled()
    expect(replaceMock).toHaveBeenCalledTimes(1)
    expect(String(replaceMock.mock.calls[0][0])).toContain('_refresh=')
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
  resetPwaForTests()
  vi.unstubAllGlobals()
})
