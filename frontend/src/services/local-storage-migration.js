/**
 * One-time migration of the reference application's localStorage keys.
 *
 * Guarded by the `migrated_from_localstorage` metadata key. The original keys
 * are left in place so an older tab or a rollback still sees its preferences.
 */

import { getMetadata, setMetadata } from './db'
import { groupIdsSchema, recentGroupsSchema } from '../utils/recent-groups'

export const MIGRATION_VERSION = 1

const SELECTION_KEYS = new Set(['recentGroups', 'starredGroups', 'archivedGroups'])
const SELECTION_SUFFIXES = ['-activeUser', '-newUser', '-defaultSplittingOptions']

/**
 * Remove the reference app's per-account selection keys. Called when the
 * authenticated identity changes so one account's group list and active users
 * are not shown to the next account on the same browser.
 *
 * @param {Storage} [storage]
 */
export function clearLegacySelectionKeys(storage = globalThis.localStorage) {
  if (!storage) return
  /** @type {string[]} */
  const keys = []
  try {
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index)
      if (!key) continue
      if (SELECTION_KEYS.has(key) || SELECTION_SUFFIXES.some((suffix) => key.endsWith(suffix))) {
        keys.push(key)
      }
    }
  } catch {
    return
  }
  for (const key of keys) {
    try {
      storage.removeItem(key)
    } catch {
      // A read-only storage implementation must not block account cleanup.
    }
  }
}

/**
 * @param {Storage} storage
 * @returns {{recentGroups: any[], starredGroups: string[], archivedGroups: string[], activeUser: Record<string, string>, newUser: Record<string, string>, newGroupActiveUser: string|null, splittingOptions: Record<string, any>}}
 */
export function readLegacyPreferences(storage) {
  /** @type {any[]} */
  let recentGroups = []
  /** @type {string[]} */
  let starredGroups = []
  /** @type {string[]} */
  let archivedGroups = []
  try {
    const recent = storage.getItem('recentGroups')
    if (recent) {
      const parsed = recentGroupsSchema.safeParse(JSON.parse(recent))
      if (parsed.success) recentGroups = parsed.data
    }
    const starred = storage.getItem('starredGroups')
    if (starred) {
      const parsed = groupIdsSchema.safeParse(JSON.parse(starred))
      if (parsed.success) starredGroups = parsed.data
    }
    const archived = storage.getItem('archivedGroups')
    if (archived) {
      const parsed = groupIdsSchema.safeParse(JSON.parse(archived))
      if (parsed.success) archivedGroups = parsed.data
    }
  } catch {
    // Corrupt legacy JSON is treated as absent.
  }

  /** @type {Record<string, string>} */
  const activeUser = {}
  /** @type {Record<string, string>} */
  const newUser = {}
  /** @type {Record<string, any>} */
  const splittingOptions = {}
  let newGroupActiveUser = null
  try {
    newGroupActiveUser = storage.getItem('newGroup-activeUser')
  } catch {
    newGroupActiveUser = null
  }

  try {
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index)
      if (!key) continue
      if (key.endsWith('-activeUser')) {
        const groupId = key.slice(0, -'-activeUser'.length)
        if (groupId && groupId !== 'newGroup') {
          const value = storage.getItem(key)
          if (value !== null) activeUser[groupId] = value
        }
      } else if (key.endsWith('-newUser')) {
        const groupId = key.slice(0, -'-newUser'.length)
        const value = storage.getItem(key)
        if (groupId && value !== null) newUser[groupId] = value
      } else if (key.endsWith('-defaultSplittingOptions')) {
        const groupId = key.slice(0, -'-defaultSplittingOptions'.length)
        const value = storage.getItem(key)
        if (!groupId || value === null) continue
        try {
          splittingOptions[groupId] = JSON.parse(value)
        } catch {
          splittingOptions[groupId] = value
        }
      }
    }
  } catch {
    // A storage implementation may deny key enumeration.
  }

  return {
    recentGroups,
    starredGroups,
    archivedGroups,
    activeUser,
    newUser,
    newGroupActiveUser,
    splittingOptions,
  }
}

/**
 * @param {Storage} [storage]
 * @returns {Promise<boolean>} true when data was migrated
 */
export async function migrateLocalStorage(storage = globalThis.localStorage) {
  if (!storage) return false
  const current = Number(await getMetadata('migrated_from_localstorage', 0) || 0)
  if (current >= MIGRATION_VERSION) return false
  const legacy = readLegacyPreferences(storage)
  await setMetadata('recentGroups', legacy.recentGroups)
  await setMetadata('starredGroups', legacy.starredGroups)
  await setMetadata('archivedGroups', legacy.archivedGroups)
  await setMetadata('activeUser', legacy.activeUser)
  await setMetadata('newUser', legacy.newUser)
  await setMetadata('newGroupActiveUser', legacy.newGroupActiveUser)
  await setMetadata('defaultSplittingOptions', legacy.splittingOptions)
  await setMetadata('migrated_from_localstorage', MIGRATION_VERSION)
  return true
}
