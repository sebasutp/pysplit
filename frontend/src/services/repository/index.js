/**
 * Single repository entry point.
 *
 * M2 selects the Dexie-backed local repository. Hooks and components keep
 * importing this module only; the online implementation stays available behind
 * it for one-off online-only operations.
 */

import { localRepository } from './local'
import { initialSyncStatus, subscribeSyncStatus } from '../sync-events'
import {
  discardFailed as discardFailedOperations,
  listConflicts as listSyncConflicts,
  resolveConflict as resolveSyncConflict,
  retryFailed as retryFailedOperations,
  startSync,
  syncNow,
} from '../sync'
import { exportBackupJson, importBackupJson } from '../backup'

export { RepositoryError } from './contract'
export { initialSyncStatus, subscribeSyncStatus, startSync, syncNow }

/** Runtime synchronization facade for status UI and conflict dialogs. */
export const sync = {
  /** @returns {Promise<any[]>} */
  conflicts: listSyncConflicts,
  /**
   * @param {number} conflictId
   * @param {'mine'|'server'|'duplicate'} strategy
   * @returns {Promise<void>}
   */
  resolveConflict: resolveSyncConflict,
  /** @returns {Promise<string>} */
  backup: exportBackupJson,
  /** @param {string} json @returns {Promise<void>} */
  restore: importBackupJson,
  /** @returns {Promise<void>} */
  retryFailed: retryFailedOperations,
  /** @returns {Promise<void>} */
  discardFailed: discardFailedOperations,
}

export const repository = /** @type {typeof localRepository & {sync: typeof sync}} */ (
  Object.assign(localRepository, { sync })
)
