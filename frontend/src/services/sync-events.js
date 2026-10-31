/**
 * Tiny observable used by the sync engine and the status UI.
 *
 * Hooks subscribe through `services/repository`; they never import this file.
 */

/** @typedef {'idle'|'syncing'|'offline'|'error'|'conflict'} SyncPhase */

/** @type {{phase: SyncPhase, pending: number, failed: number, conflicts: number, lastError: string|null, online: boolean, lastSyncedAt: string|null}} */
export const initialSyncStatus = {
  phase: 'idle',
  pending: 0,
  failed: 0,
  conflicts: 0,
  lastError: null,
  online: typeof navigator === 'undefined' ? true : navigator.onLine !== false,
  lastSyncedAt: null,
}

let status = { ...initialSyncStatus }
const listeners = new Set()

/** @param {Partial<typeof status>} patch */
export function setSyncStatus(patch) {
  status = { ...status, ...patch }
  for (const listener of listeners) {
    try {
      listener(status)
    } catch {
      // A broken subscriber must not stop the sync engine.
    }
  }
}

/** @returns {typeof status} */
export function getSyncStatus() {
  return status
}

/**
 * @param {(value: typeof status) => void} listener
 * @returns {() => void}
 */
export function subscribeSyncStatus(listener) {
  listeners.add(listener)
  listener(status)
  return () => listeners.delete(listener)
}
