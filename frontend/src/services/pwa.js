/**
 * Service-worker registration and the explicit update lifecycle.
 *
 * The worker waits after an update is found. Nothing calls skipWaiting until
 * the user presses Reload, and before activating we verify the local Dexie
 * schema opens and compare the waiting build's emitted schema contract so
 * pending outbox rows are less likely to be stranded by a bad upgrade.
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
 * Register the generated service worker. Safe to call more than once.
 *
 * @param {{
 *   force?: boolean,
 *   register?: (options: Record<string, any>) => (reloadPage?: boolean) => Promise<void>,
 * }} [options]
 */
export function startPwa(options = {}) {
  if (started) return
  if (!options.force && !import.meta.env.PROD) return
  if (!pwaSupported()) return
  started = true

  const register = options.register || registerSW
  try {
    const updateServiceWorker = register({
      immediate: true,
      onNeedRefresh() {
        update({ needRefresh: true, error: null })
      },
      onOfflineReady() {
        update({ offlineReady: true })
      },
      onRegisteredSW(/** @type {string} */ _url, /** @type {any} */ registration) {
        update({ registration: registration || null })
      },
      onRegisterError(/** @type {any} */ error) {
        update({
          error: error instanceof Error ? error.message : 'Service worker registration failed',
        })
      },
    })
    update({ updateServiceWorker })
    void cleanupOutdatedRuntimeCaches().catch(() => {})
  } catch (error) {
    update({
      error: error instanceof Error ? error.message : 'Service worker registration failed',
    })
  }
}

/**
 * Activate a waiting update after an explicit user action.
 *
 * The Dexie probes run first: the current database must still open and the
 * waiting build must declare a compatible schema contract. If either check
 * fails, reloading would replace the UI without a usable cache. The error
 * stays visible so the user can export a backup before trying again.
 *
 * @returns {Promise<boolean>} true when the update was handed to Workbox
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
  if (state.updateServiceWorker) {
    await state.updateServiceWorker(true)
    return true
  }
  if (typeof window !== 'undefined') window.location.reload()
  return true
}

/** Test-only helper: reset module state between cases. */
export function resetPwaForTests() {
  started = false
  state = { ...initialState }
}
