/**
 * Service-worker registration and the update lifecycle.
 *
 * A new worker waits after an update is found. Activation is gated by the
 * Dexie compatibility checks below, then either the automatic online path or
 * the manual prompt sends SKIP_WAITING. The worker claims clients on activation
 * so open pages receive controllerchange and reload into the new build.
 */

import { registerSW } from 'virtual:pwa-register'

import { CACHE_NAMES } from '../../pwa.config.js'
import {
  fetchIncomingBuildContract,
  verifyDatabaseCompatibility,
  verifyIncomingBuildCompatibility,
} from './db'

/**
 * @typedef {Object} PwaState
 * @property {boolean} needRefresh
 * @property {boolean} offlineReady
 * @property {string|null} error
 * @property {ServiceWorkerRegistration|null} registration
 * @property {((reloadPage?: boolean) => Promise<void>)|null} updateServiceWorker
 */

/** @type {PwaState} */
const initialState = {
  needRefresh: false,
  offlineReady: false,
  error: null,
  registration: null,
  updateServiceWorker: null,
}

let state = { ...initialState }
const listeners = new Set()
let started = false

const UPDATE_POLL_MS = 12 * 60 * 1000
const ACTIVATION_TIMEOUT_MS = 5000
let reloadRequested = false
/** @type {ReturnType<typeof setInterval>|null} */
let pollTimer = null
let listenersAttached = false
/** @type {any} */
let currentRegistration = null
let autoActivationInFlight = false
let autoActivationFailed = false
/** @type {(() => void)|null} */
let onlineHandler = null
/** @type {(() => void)|null} */
let focusHandler = null
/** @type {(() => void)|null} */
let visibilityHandler = null

/** @param {Partial<PwaState>} patch */
function update(patch) {
  state = { ...state, ...patch }
  for (const listener of listeners) {
    try {
      listener(state)
    } catch {
      // A broken subscriber must not break registration.
    }
  }
}

/** @returns {PwaState} */
export function getPwaState() {
  return state
}

/** @param {(value: PwaState) => void} listener @returns {() => void} */
export function subscribePwa(listener) {
  listeners.add(listener)
  listener(state)
  return () => listeners.delete(listener)
}

/** @returns {boolean} */
export function pwaSupported() {
  return typeof navigator !== 'undefined' && 'serviceWorker' in navigator
}

/**
 * Delete runtime caches from older builds. `cleanupOutdatedCaches` only
 * handles Workbox precache entries, not the custom image/font cache names.
 *
 * @returns {Promise<string[]>} names deleted
 */
export async function cleanupOutdatedRuntimeCaches() {
  if (typeof caches === 'undefined') return []
  const keep = new Set(Object.values(CACHE_NAMES))
  const prefixes = ['pysplit-images-', 'pysplit-fonts-']
  const names = await caches.keys()
  const stale = names.filter(
    (name) => prefixes.some((prefix) => name.startsWith(prefix)) && !keep.has(name),
  )
  await Promise.all(stale.map((name) => caches.delete(name)))
  return stale
}

/**
 * Force the browser to fetch the latest app shell.
 *
 * When online, best-effort unregister every service worker and clear Cache
 * Storage before reloading with a cache-busting query parameter. While offline
 * the cached app is the only usable copy, so workers and caches are left alone
 * and only the reload happens. IndexedDB, localStorage and all other user data
 * are deliberately untouched.
 *
 * @returns {Promise<void>}
 */
export async function forceRefreshApp() {
  if (browserOnline()) {
    if (pwaSupported()) {
      try {
        const registrations = await navigator.serviceWorker.getRegistrations()
        await Promise.all(registrations.map((registration) => registration.unregister()))
      } catch {
        // Best effort: continue to the reload below.
      }
    }
    if (typeof caches !== 'undefined') {
      try {
        const names = await caches.keys()
        await Promise.all(names.map((name) => caches.delete(name)))
      } catch {
        // Best effort: continue to the reload below.
      }
    }
  }
  if (typeof window !== 'undefined' && window.location) {
    try {
      const url = new URL(window.location.href)
      url.searchParams.set('_refresh', String(Date.now()))
      window.location.replace(url.toString())
    } catch {
      window.location.reload()
    }
  }
}

/**
 * Remove a leftover production service worker and its caches in development.
 *
 * A browser that loaded the built SPA on the same origin keeps controlling the
 * page until that worker is unregistered. Vite cannot replace its responses, so
 * developers would keep seeing the stale bundle even after the source changed.
 *
 * @returns {Promise<void>}
 */
async function clearDevelopmentServiceWorkers() {
  if (!pwaSupported()) return
  try {
    const registrations = await navigator.serviceWorker.getRegistrations()
    await Promise.all(registrations.map((registration) => registration.unregister()))
    if (typeof caches !== 'undefined') {
      const names = await caches.keys()
      await Promise.all(names.map((name) => caches.delete(name)))
    }
  } catch {
    // Best effort: failure here must not stop the development app from loading.
  }
}

/**
 * Whether the browser reports a connection. Undefined means assume online.
 *
 * @returns {boolean}
 */
function browserOnline() {
  return typeof navigator === 'undefined' || navigator.onLine !== false
}

function stopUpdateChecks() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (typeof window !== 'undefined') {
    if (onlineHandler) window.removeEventListener('online', onlineHandler)
    if (focusHandler) window.removeEventListener('focus', focusHandler)
  }
  if (typeof document !== 'undefined' && visibilityHandler) {
    document.removeEventListener('visibilitychange', visibilityHandler)
  }
  listenersAttached = false
  onlineHandler = null
  focusHandler = null
  visibilityHandler = null
  currentRegistration = null
}

async function checkForUpdate() {
  if (!browserOnline() || typeof currentRegistration?.update !== 'function') return
  try {
    await currentRegistration.update()
  } catch {
    // A transient update check failure must not surface as an app error.
  }
}

/**
 * Activate a waiting update automatically, but only once per update and only
 * while online. Compatibility failures keep the manual prompt visible.
 */
async function maybeAutoActivate() {
  if (!state.needRefresh || autoActivationInFlight || autoActivationFailed) return
  if (!browserOnline()) return
  autoActivationInFlight = true
  try {
    // Let onNeedRefresh finish publishing state before the async checks start.
    await Promise.resolve()
    if (!state.needRefresh) return
    const activated = await activateUpdate()
    if (!activated) autoActivationFailed = true
  } catch (error) {
    autoActivationFailed = true
    update({
      error:
        error instanceof Error ? error.message : 'The update could not be activated',
    })
  } finally {
    autoActivationInFlight = false
  }
}

/** @param {any} registration */
function startUpdateChecks(registration) {
  if (!registration || typeof registration.update !== 'function') return
  currentRegistration = registration
  if (pollTimer !== null) clearInterval(pollTimer)
  pollTimer = setInterval(() => {
    void checkForUpdate()
  }, UPDATE_POLL_MS)
}

function attachUpdateListeners() {
  if (listenersAttached) return
  listenersAttached = true
  if (typeof window !== 'undefined') {
    onlineHandler = () => {
      void checkForUpdate()
      void maybeAutoActivate()
    }
    focusHandler = () => {
      void checkForUpdate()
      void maybeAutoActivate()
    }
    window.addEventListener('online', onlineHandler)
    window.addEventListener('focus', focusHandler)
  }
  if (typeof document !== 'undefined') {
    visibilityHandler = () => {
      if (document.visibilityState === 'visible') {
        void checkForUpdate()
        void maybeAutoActivate()
      }
    }
    document.addEventListener('visibilitychange', visibilityHandler)
  }
}

/**
 * Register the generated service worker. Safe to call more than once.
 *
 * @param {{
 *   force?: boolean,
 *   register?: (options: Record<string, any>) => ((reloadPage?: boolean) => Promise<void>) | undefined,
 * }} [options]
 */
export function startPwa(options = {}) {
  if (!options.force && !import.meta.env.PROD) {
    if (started) return
    started = true
    void clearDevelopmentServiceWorkers()
    return
  }
  if (started) return
  if (!pwaSupported()) return
  started = true

  const register = options.register || registerSW
  try {
    const updateServiceWorker = register({
      immediate: true,
      onNeedRefresh() {
        update({ needRefresh: true, error: null })
        autoActivationFailed = false
        void maybeAutoActivate()
      },
      onOfflineReady() {
        update({ offlineReady: true })
      },
      onRegisteredSW(/** @type {string} */ _url, /** @type {any} */ registration) {
        update({ registration: registration || null })
        startUpdateChecks(registration)
      },
      onRegisterError(/** @type {any} */ error) {
        update({
          error: error instanceof Error ? error.message : 'Service worker registration failed',
        })
      },
    })
    update({ updateServiceWorker })
    attachUpdateListeners()
    void cleanupOutdatedRuntimeCaches().catch(() => {})
  } catch (error) {
    update({
      error: error instanceof Error ? error.message : 'Service worker registration failed',
    })
  }
}

/**
 * Reload the page at most once for this activation attempt.
 *
 * @returns {boolean} whether the reload was handed to the browser
 */
function reloadPageOnce() {
  if (reloadRequested) return true
  reloadRequested = true
  if (typeof window !== 'undefined' && window.location) {
    try {
      window.location.reload()
      return true
    } catch {
      return false
    }
  }
  return false
}

/**
 * Wait briefly for the new worker to take control of this page.
 *
 * @returns {{promise: Promise<boolean>, cancel: () => void}}
 */
function watchControllerChange() {
  if (
    !pwaSupported() ||
    typeof navigator.serviceWorker.addEventListener !== 'function'
  ) {
    return { promise: Promise.resolve(false), cancel: () => {} }
  }
  let settled = false
  /** @type {ReturnType<typeof setTimeout>|undefined} */
  let timer
  /** @type {(value: boolean) => void} */
  let resolve = () => {}
  /** @param {boolean} changed */
  const finish = (changed) => {
    if (settled) return
    settled = true
    if (timer !== undefined) clearTimeout(timer)
    navigator.serviceWorker.removeEventListener?.('controllerchange', onChange)
    resolve(changed)
  }
  const onChange = () => finish(true)
  const promise = new Promise((/** @type {(value: boolean) => void} */ done) => {
    resolve = done
  })
  timer = setTimeout(() => finish(false), ACTIVATION_TIMEOUT_MS)
  navigator.serviceWorker.addEventListener('controllerchange', onChange)
  return { promise, cancel: () => finish(false) }
}

/**
 * Activate a waiting update after compatibility checks pass.
 *
 * The Dexie probes run first: the current database must still open and the
 * waiting build must declare a compatible schema contract. If either check
 * fails, reloading would replace the UI without a usable cache. The error
 * stays visible so the user can export a backup before trying again.
 *
 * Activation is only reported as successful once `controllerchange` confirms
 * that the new worker took control. The page is then reloaded explicitly when
 * the updater did not already do so.
 *
 * @returns {Promise<boolean>} true when the update was confirmed
 */
export async function activateUpdate() {
  if (!state.needRefresh) return false
  try {
    await verifyDatabaseCompatibility()
    const contract = await fetchIncomingBuildContract()
    await verifyIncomingBuildCompatibility(contract)
  } catch (error) {
    update({
      error:
        error instanceof Error
          ? `Update compatibility check failed: ${error.message}`
          : 'Update compatibility check failed',
    })
    return false
  }

  const watch = watchControllerChange()
  try {
    if (state.updateServiceWorker) {
      // Pass false so Workbox does not install its own controlling handler.
      // This module waits for controllerchange and performs the single reload.
      await state.updateServiceWorker(false)
    } else if (currentRegistration?.waiting) {
      currentRegistration.waiting.postMessage({ type: 'SKIP_WAITING' })
    } else {
      watch.cancel()
      update({ error: 'No waiting update is available to activate.' })
      autoActivationFailed = true
      return false
    }
  } catch (error) {
    watch.cancel()
    update({
      error:
        error instanceof Error ? error.message : 'The update could not be activated',
    })
    autoActivationFailed = true
    return false
  }

  const changed = await watch.promise
  if (!changed) {
    update({
      error: 'The update did not activate in time. Reload to try again.',
    })
    autoActivationFailed = true
    return false
  }
  if (!reloadPageOnce()) {
    update({ error: 'The update could not reload the page. Reload manually.' })
    autoActivationFailed = true
    return false
  }
  return true
}

/** Test-only helper: reset module state between cases. */
export function resetPwaForTests() {
  stopUpdateChecks()
  started = false
  autoActivationInFlight = false
  autoActivationFailed = false
  reloadRequested = false
  state = { ...initialState }
}
