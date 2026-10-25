/**
 * Reference-compatible localStorage helpers for the group list.
 *
 * These keys are migrated into Dexie in Stage 9C. Until then the SPA reads and
 * writes the same shapes as the Next.js application so existing browser
 * profiles keep their recent/starred/archived lists.
 */

import { z } from 'zod'

export const recentGroupsSchema = z.array(
  z.object({
    id: z.string().min(1),
    name: z.string(),
  }),
)

export const groupIdsSchema = z.array(z.string().min(1))

/** @typedef {z.infer<typeof recentGroupsSchema>[number]} RecentGroup */

const RECENT_KEY = 'recentGroups'
const STARRED_KEY = 'starredGroups'
const ARCHIVED_KEY = 'archivedGroups'

/** @param {string} key @returns {string | null} */
function read(key) {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

/** @param {string} key @param {unknown} value */
function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Private mode or a full quota must not break navigation.
  }
}

/** @returns {RecentGroup[]} */
export function getRecentGroups() {
  const raw = read(RECENT_KEY)
  if (!raw) return []
  try {
    const parsed = recentGroupsSchema.safeParse(JSON.parse(raw))
    return parsed.success ? parsed.data : []
  } catch {
    return []
  }
}

/** @param {RecentGroup} group */
export function saveRecentGroup(group) {
  const recent = getRecentGroups()
  write(RECENT_KEY, [group, ...recent.filter((item) => item.id !== group.id)])
}

/** @param {string} groupId */
export function deleteRecentGroup(groupId) {
  write(
    RECENT_KEY,
    getRecentGroups().filter((item) => item.id !== groupId),
  )
}

/** @returns {string[]} */
export function getStarredGroups() {
  return readIds(STARRED_KEY)
}

/** @param {string} groupId */
export function starGroup(groupId) {
  write(STARRED_KEY, [...new Set([...getStarredGroups(), groupId])])
}

/** @param {string} groupId */
export function unstarGroup(groupId) {
  write(
    STARRED_KEY,
    getStarredGroups().filter((id) => id !== groupId),
  )
}

/** @returns {string[]} */
export function getArchivedGroups() {
  return readIds(ARCHIVED_KEY)
}

/** @param {string} groupId */
export function archiveGroup(groupId) {
  write(ARCHIVED_KEY, [...new Set([...getArchivedGroups(), groupId])])
}

/** @param {string} groupId */
export function unarchiveGroup(groupId) {
  write(
    ARCHIVED_KEY,
    getArchivedGroups().filter((id) => id !== groupId),
  )
}

/** @param {string} key @returns {string[]} */
function readIds(key) {
  const raw = read(key)
  if (!raw) return []
  try {
    const parsed = groupIdsSchema.safeParse(JSON.parse(raw))
    return parsed.success ? parsed.data : []
  } catch {
    return []
  }
}

/** @param {string} groupId @returns {string | null} */
export function getActiveUser(groupId) {
  const value = read(`${groupId}-activeUser`)
  if (!value || value === 'None') return null
  return value
}

/** @param {string} groupId @param {string | null} participantId */
export function setActiveUser(groupId, participantId) {
  try {
    localStorage.setItem(`${groupId}-activeUser`, participantId || 'None')
  } catch {
    // ignored
  }
}

/** @returns {string | null} */
export function getPendingActiveUser() {
  const value = read('newGroup-activeUser')
  if (!value || value === 'None') return null
  return value
}

/** @param {string | null} value */
export function setPendingActiveUser(value) {
  try {
    localStorage.setItem('newGroup-activeUser', value || 'None')
  } catch {
    // ignored
  }
}
