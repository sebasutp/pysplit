// @ts-nocheck
// Dexie tables are untyped at runtime; the repository contract tests cover shapes.
/**
 * Local-first repository backed by Dexie.
 *
 * Reads come from IndexedDB. Writes are applied locally and appended to the
 * outbox in one transaction, then pushed when the browser is online. The
 * method surface is identical to `online.js` (docs/repository-contract.md).
 */

import { DEFAULT_CATEGORIES } from '../../utils/categories'
import {
  getBalances,
  getPublicBalances,
  getSuggestedReimbursements,
} from '../../utils/domain/balances'
import { formatAmountAsDecimal, formatAmountForCsv } from '../../utils/domain/currency'
import { computeReceiptSplit, toReceiptSplitItems } from '../../utils/domain/receipt-split'
import { getExpenseShares } from '../../utils/domain/shares'
import {
  filterExpensesByDateRange,
  getExpensesByCategory,
  getExpensesByMonth,
  getRecurringSpending,
  getSpendingByCategory,
  getSpendingByParticipant,
  getSpendingOverTime,
  getSpendingSummary,
  getTotalActiveUserPaidFor,
  getTotalActiveUserShare,
  getTotalGroupSpending,
} from '../../utils/domain/totals'
import {
  db,
  clearAllData,
  composeGroup,
  deleteLocalGroup,
  getMetadata,
  isOnline,
  liveExpenses,
  liveParticipants,
  newId,
  nowIso,
  readExpense,
  readExpenses,
  readGroup,
  setMetadata,
} from '../db'
import {
  clearLegacySelectionKeys,
  migrateLocalStorage,
} from '../local-storage-migration'
import { enqueue } from '../outbox'
import {
  scheduleSync,
  startSync,
  stopSync,
  pushPending,
  bootstrapGroup,
  prefetchGroups,
} from '../sync'
import { RepositoryError, run } from './contract'
import { onlineRepository } from './online'

const SYNC_INTERVAL = 30_000

/** @type {Promise<void>|null} */
let readyPromise = null
/** @type {Promise<any>|null} */
let groupsSyncPromise = null
/** @type {Map<string, Promise<any>>} */
const groupLoading = new Map()

/** Ensure Dexie is open, legacy preferences are migrated and categories exist. */
export function ready() {
  if (!readyPromise) {
    readyPromise = (async () => {
      await db.open()
      try {
        await migrateLocalStorage()
      } catch {
        // Private mode or denied storage: start with an empty preference set.
      }
      if ((await db.categories.count()) === 0) {
        await db.categories.bulkPut(DEFAULT_CATEGORIES)
      }
    })()
  }
  return readyPromise
}

/** @param {any} user */
export async function cacheUser(user) {
  const next = user || null
  const previous = await getMetadata('session_user', null)
  if ((previous?.id || null) !== (next?.id || null)) {
    // Never let one account's cache, outbox, conflicts or selection keys leak
    // into another account on the same browser.
    await stopSync()
    await clearAllData()
    await db.categories.bulkPut(DEFAULT_CATEGORIES)
    clearLegacySelectionKeys()
    groupsSyncPromise = null
    groupLoading.clear()
    accessRecordedAt.clear()
    lastRefresh = null
  }
  if (next) {
    await setMetadata('session_user', next)
    await setMetadata('session_user_cached_at', nowIso())
  } else {
    await setMetadata('session_user', null)
  }
  if ((previous?.id || null) !== (next?.id || null)) startSync()
}

/** @returns {Promise<any|null>} */
export async function cachedUser() {
  await ready()
  return getMetadata('session_user', null)
}

/** @param {any} user @returns {boolean} */
function canCreateFromCache(user) {
  return Boolean(user && ['group_creators', 'admin'].includes(user.tier))
}

/**
 * @param {string[]} extraIds
 * @returns {Promise<string[]>}
 */
async function knownGroupIds(extraIds = []) {
  const metadataRecent = (await getMetadata('recentGroups', [])) || []
  const ids = new Set([
    ...(await db.groups.toCollection().primaryKeys()).map(String),
    ...metadataRecent.map((group) => group.id),
    ...extraIds,
  ])
  return [...ids].filter(Boolean)
}

/**
 * @param {any} group
 */
async function rememberRecent(group) {
  const recent = (await getMetadata('recentGroups', [])) || []
  const next = [
    { id: group.id, name: group.name },
    ...recent.filter((item) => item.id !== group.id),
  ].slice(0, 50)
  await setMetadata('recentGroups', next)
}


/**
 * Cache the authenticated group list. Rows written here are marked
 * `list_only` because the response carries no expenses, balances or receipts;
 * `ensureGroup` bootstraps them before serving those screens.
 *
 * @param {any} result
 */
async function cacheSyncResult(result) {
  const groups = Array.isArray(result?.groups) ? result.groups : []
  const authenticated = Boolean(result.is_authenticated ?? result.isAuthenticated)
  const metadataRecent = (await getMetadata('recentGroups', [])) || []
  const starred = new Set(await getMetadata('starredGroups', []))
  const archived = new Set(await getMetadata('archivedGroups', []))
  const outbox = await db.outbox.toArray()
  const pendingGroupCreates = new Set(
    outbox
      .filter((operation) => operation.entity_type === 'group' && operation.op_type === 'create')
      .map((operation) => operation.group_id),
  )
  const pendingMembershipDeletes = new Set(
    outbox
      .filter((operation) => operation.entity_type === 'user_group' && operation.op_type === 'delete')
      .map((operation) => operation.group_id),
  )
  const returnedIds = new Set(groups.map((group) => group.id))
  const pruned = authenticated
    ? (await db.groups.toCollection().primaryKeys())
        .map(String)
        .filter((id) => !returnedIds.has(id) && !pendingGroupCreates.has(id))
    : []
  await db.transaction(
    'rw',
    [db.groups, db.participants, db.userGroups, db.metadata],
    async () => {
      for (const group of groups) {
        // A pending "leave group" must not be undone by a list response that
        // raced the push.
        if (pendingMembershipDeletes.has(group.id)) continue
        const existing = await db.groups.get(group.id)
        const base = existing?.pending ? existing : group
        await db.groups.put({
          ...base,
          participants: undefined,
          user_group: undefined,
          is_starred: undefined,
          is_archived: undefined,
          isStarred: undefined,
          isArchived: undefined,
          pending: Boolean(existing?.pending),
          // A full bootstrap is the only writer that clears `list_only`.
          list_only: existing?.cached_at ? Boolean(existing?.list_only) : true,
          cached_at: existing?.cached_at ?? null,
        })
        const participants = Array.isArray(group.participants) ? group.participants : []
        const pendingParticipants = await db.participants
          .where('group_id')
          .equals(group.id)
          .filter((row) => Boolean(row.pending))
          .toArray()
        await db.participants.where('group_id').equals(group.id).delete()
        if (participants.length) {
          await db.participants.bulkPut(
            participants.map((participant, index) => ({
              ...participant,
              group_id: group.id,
              position: index,
              pending: false,
            })),
          )
        }
        if (pendingParticipants.length) {
          await db.participants.bulkPut(
            pendingParticipants.map((participant) => ({ ...participant, pending: true })),
          )
        }
        if (group.user_group) {
          await db.userGroups.put({
            ...group.user_group,
            id: `${group.user_group.user_id}:${group.user_group.group_id}`,
          })
        }
        if (group.is_starred ?? group.isStarred) starred.add(group.id)
        else if (authenticated) starred.delete(group.id)
        if (group.is_archived ?? group.isArchived) archived.add(group.id)
        else if (authenticated) archived.delete(group.id)
        if (!metadataRecent.some((/** @type {any} */ item) => item.id === group.id)) {
          metadataRecent.push({ id: group.id, name: group.name })
        }
      }
      for (const id of pruned) {
        starred.delete(id)
        archived.delete(id)
      }
      const recent = metadataRecent.filter(
        (entry) =>
          !pruned.includes(entry.id) &&
          (!authenticated || returnedIds.has(entry.id) || pendingGroupCreates.has(entry.id)),
      )
      await db.metadata.put({
        key: 'recentGroups',
        value: recent.slice(0, 50),
        updated_at: nowIso(),
      })
      await db.metadata.put({
        key: 'starredGroups',
        value: [...starred],
        updated_at: nowIso(),
      })
      await db.metadata.put({
        key: 'archivedGroups',
        value: [...archived],
        updated_at: nowIso(),
      })
    },
  )
  for (const groupId of pruned) {
    await deleteLocalGroup(groupId)
  }
}

/**
 * @param {string} groupId
 * @returns {Promise<any|null>}
 */
async function ensureGroup(groupId) {
  await ready()
  const cached = await readGroup(groupId)
  // A group-list row only contains the group and its participants. Any screen
  // that needs expenses, balances, stats or receipts must bootstrap it first.
  if (cached && !cached.list_only) return cached
  if (!isOnline()) return cached
  if (groupLoading.has(groupId)) return groupLoading.get(groupId)
  const task = (async () => {
    try {
      await bootstrapGroup(groupId)
    } catch (error) {
      if (error && typeof error === 'object' && 'code' in error) {
        if (error.code === 'not_found' || error.code === 'forbidden') {
          await deleteLocalGroup(groupId)
          return null
        }
        if (!['aborted', 'conflict'].includes(String(error.code)) && cached) {
          // Keep the list row visible while the network is unavailable; the
          // next read or refresh will retry the bootstrap.
          return cached
        }
      }
      throw error
    }
    return readGroup(groupId)
  })().finally(() => groupLoading.delete(groupId))
  groupLoading.set(groupId, task)
  return task
}

/**
 * @param {string} groupId
 * @returns {Promise<any>}
 */
async function requireGroup(groupId) {
  const group = await ensureGroup(groupId)
  if (!group) throw new RepositoryError('Group not found', { code: 'not_found', status: 404 })
  return group
}

/** @type {Map<string, number>} */
const accessRecordedAt = new Map()

/**
 * @param {string} groupId
 */
async function recordAccessDebounced(groupId) {
  const last = accessRecordedAt.get(groupId) || 0
  if (Date.now() - last < 60_000) return
  accessRecordedAt.set(groupId, Date.now())
  await onlineRepository.groups.recordAccess(groupId).catch(() => {})
}

/**
 * @param {any} group
 * @returns {Promise<any>}
 */
async function composeCachedGroup(group) {
  if (!group) return null
  const [participants, memberships, starred, archived] = await Promise.all([
    liveParticipants(group.id),
    db.userGroups.where('group_id').equals(group.id).toArray(),
    getMetadata('starredGroups', []),
    getMetadata('archivedGroups', []),
  ])
  const user = await cachedUser()
  const membership = user
    ? memberships.find((row) => row.user_id === user.id) || null
    : null
  const composed = composeGroup(group, membership, participants)
  if (!membership) {
    // Guests (and capability-URL visitors without a membership row) keep
    // star/archive state in Dexie metadata.
    const isStarred = (starred || []).includes(group.id)
    const isArchived = (archived || []).includes(group.id)
    composed.is_starred = isStarred
    composed.is_archived = isArchived
    composed.isStarred = isStarred
    composed.isArchived = isArchived
  }
  return composed
}

/**
 * @param {string[]} extraIds
 * @returns {Promise<any[]>}
 */
async function cachedGroups(extraIds = []) {
  const ids = await knownGroupIds(extraIds)
  const rows = ids.length ? await db.groups.where('id').anyOf(ids).toArray() : []
  const live = rows.filter((row) => !row.deleted_at)
  const groupIds = live.map((row) => row.id)
  const [allParticipants, allMemberships, user, starredRows, archivedRows] = await Promise.all([
    groupIds.length
      ? db.participants.where('group_id').anyOf(groupIds).toArray()
      : [],
    groupIds.length ? db.userGroups.where('group_id').anyOf(groupIds).toArray() : [],
    cachedUser(),
    getMetadata('starredGroups', []),
    getMetadata('archivedGroups', []),
  ])
  const participantsByGroup = new Map()
  for (const participant of allParticipants) {
    if (participant.deleted_at) continue
    const list = participantsByGroup.get(participant.group_id) || []
    list.push(participant)
    participantsByGroup.set(participant.group_id, list)
  }
  const membershipsByGroup = new Map()
  for (const membership of allMemberships) {
    const list = membershipsByGroup.get(membership.group_id) || []
    list.push(membership)
    membershipsByGroup.set(membership.group_id, list)
  }
  const starred = new Set(starredRows || [])
  const archived = new Set(archivedRows || [])
  const groups = live.map((row) => {
    const participants = (participantsByGroup.get(row.id) || []).sort(
      (first, second) => Number(first.position ?? 0) - Number(second.position ?? 0),
    )
    const memberships = membershipsByGroup.get(row.id) || []
    const membership = user
      ? memberships.find((entry) => entry.user_id === user.id) || null
      : null
    const composed = composeGroup(row, membership, participants)
    if (!membership) {
      const isStarred = starred.has(row.id)
      const isArchived = archived.has(row.id)
      composed.is_starred = isStarred
      composed.is_archived = isArchived
      composed.isStarred = isStarred
      composed.isArchived = isArchived
    }
    return composed
  })
  const seen = new Set(groups.map((group) => group.id))
  const recent = (await getMetadata('recentGroups', [])) || []
  for (const entry of recent) {
    if (seen.has(entry.id)) continue
    groups.push({
      id: entry.id,
      name: entry.name,
      information: null,
      currency: '$',
      currency_code: null,
      created_at: null,
      updated_at: null,
      version: 0,
      deleted_at: null,
      participants: [],
      participants_count: 0,
      user_group: null,
      is_starred: starred.has(entry.id),
      is_archived: archived.has(entry.id),
      isStarred: starred.has(entry.id),
      isArchived: archived.has(entry.id),
      cached_placeholder: true,
    })
  }
  return groups
}

/**
 * @param {any[]} groups
 * @param {string} status
 */
function filterGroupStatus(groups, status) {
  if (status === 'starred') return groups.filter((group) => group.is_starred)
  if (status === 'archived') return groups.filter((group) => group.is_archived)
  if (status === 'recent') {
    const active = groups.filter((group) => !group.is_archived)
    return active.sort((first, second) => {
      const firstTime = first.user_group?.created_at || first.updated_at || ''
      const secondTime = second.user_group?.created_at || second.updated_at || ''
      return firstTime < secondTime ? 1 : firstTime > secondTime ? -1 : 0
    })
  }
  // The server's default and `all` path include archived groups.
  return [...groups].sort((first, second) => {
    if (first.name !== second.name) return first.name < second.name ? -1 : 1
    const firstCreated = first.created_at || ''
    const secondCreated = second.created_at || ''
    if (firstCreated !== secondCreated) return firstCreated < secondCreated ? 1 : -1
    return first.id < second.id ? -1 : 1
  })
}

/**
 * @param {any} expense
 */
function localExpenseRecord(expense) {
  return {
    ...expense,
    pending: true,
    created_at: expense.created_at || nowIso(),
    updated_at: expense.updated_at || nowIso(),
    version: Number(expense.version || 0),
    deleted_at: null,
  }
}

/**
 * @param {unknown} value
 * @returns {number|null}
 */
function decimal(value) {
  if (value === null || value === undefined) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

/**
 * @param {string} message
 * @returns {never}
 */
function invalidPaidFor(message) {
  throw new RepositoryError(message, {
    code: 'validation',
    status: 422,
    fields: { paid_for: message },
  })
}

/**
 * Mirror the server's `normalize_paid_for` so local rows and outbox payloads
 * use the same canonical integer shares as the API.
 *
 * @param {any[]|undefined} rows
 * @param {string} splitMode
 * @param {number} amount
 * @returns {{participant_id: string, shares: number}[]}
 */
function normalizePaidFor(rows, splitMode, amount) {
  if (!Array.isArray(rows) || rows.length === 0) {
    invalidPaidFor('paid_for must contain at least one participant')
  }
  if (splitMode === 'EVENLY') {
    return rows.map((row) => ({ participant_id: row.participant_id, shares: 1 }))
  }
  if (splitMode === 'BY_AMOUNT') {
    const values = rows.map((row) => {
      const value = decimal(row.amount ?? row.shares)
      if (value === null || !Number.isInteger(value) || value <= 0) {
        invalidPaidFor('BY_AMOUNT requires positive integer amounts')
      }
      return { participant_id: row.participant_id, shares: value }
    })
    const total = values.reduce((sum, row) => sum + row.shares, 0)
    if (total !== Number(amount)) invalidPaidFor('The sum of amounts must equal the total.')
    return values
  }
  if (splitMode === 'BY_PERCENTAGE') {
    const provided = new Map(
      rows
        .filter((row) => row.percentage !== null && row.percentage !== undefined)
        .map((row) => [row.participant_id, decimal(row.percentage)]),
    )
    const plain = rows.filter((row) => row.percentage === null || row.percentage === undefined)
    const plainValues = plain.map((row) => decimal(row.shares))
    const plainTotal = plainValues.reduce((sum, value) => sum + (value || 0), 0)
    const treatPlainAsPercent =
      plain.length > 0 &&
      plainValues.every((value) => value !== null && Math.abs(value) <= 100) &&
      plainTotal <= 100
    const values = rows.map((row) => {
      const percentage = provided.get(row.participant_id)
      const raw = percentage !== undefined ? percentage : decimal(row.shares)
      if (raw === null || raw <= 0) invalidPaidFor('Percentage shares must be positive')
      if (percentage !== undefined || treatPlainAsPercent) {
        return { participant_id: row.participant_id, shares: Math.round(raw * 100) }
      }
      if (!Number.isInteger(raw)) {
        invalidPaidFor('BY_PERCENTAGE shares must be percentages or basis points')
      }
      return { participant_id: row.participant_id, shares: raw }
    })
    const total = values.reduce((sum, row) => sum + row.shares, 0)
    if (total !== 10_000) invalidPaidFor('The percentages must add up to 100%.')
    return values
  }
  return rows.map((row) => {
    const value = decimal(row.shares ?? 1)
    if (value === null || value <= 0 || !Number.isInteger(value)) {
      invalidPaidFor('Shares must be positive integers')
    }
    return { participant_id: row.participant_id, shares: value }
  })
}

/**
 * @param {any} receipt
 * @param {any[]} participants
 * @returns {Promise<any>}
 */
async function receiptState(receipt, participants) {
  const items = await db.receiptItems.where('receipt_id').equals(receipt.id).toArray()
  const visibleItems = items.filter((item) => !item.deleted_at).sort((first, second) => {
    if (Number(first.position) !== Number(second.position)) {
      return Number(first.position) - Number(second.position)
    }
    return first.id < second.id ? -1 : 1
  })
  const ids = visibleItems.map((item) => item.id)
  const portions = ids.length
    ? await db.receiptPortions.where('item_id').anyOf(ids).toArray()
    : []
  const portionsByItem = new Map()
  for (const portion of portions) {
    if (portion.deleted_at) continue
    const list = portionsByItem.get(portion.item_id) || []
    list.push(portion)
    portionsByItem.set(portion.item_id, list)
  }
  const optOuts = await db.receiptOptOuts.where('receipt_id').equals(receipt.id).toArray()
  const optedOutIds = optOuts
    .filter((row) => !row.deleted_at)
    .map((row) => row.participant_id)
  const itemsWithPortions = visibleItems.map((item) => ({
    ...item,
    portions: (portionsByItem.get(item.id) || [])
      .sort((first, second) =>
        String(first.created_at || '') < String(second.created_at || '') ? -1 : 1,
      )
      .map((portion) => ({
        id: portion.id,
        item_id: portion.item_id,
        target: portion.target,
        participant_id: portion.participant_id,
        quantity_milli: portion.quantity_milli,
        version: portion.version,
      })),
  }))
  const split = computeReceiptSplit(
    participants.map((participant) => participant.id),
    optedOutIds,
    toReceiptSplitItems(
      itemsWithPortions.map((item) => ({
        amount: item.amount,
        quantity_milli: item.quantity_milli,
        is_shared: item.is_shared,
        portions: item.portions,
      })),
    ),
  )
  const adjustments = visibleItems
    .filter((item) => item.is_adjustment)
    .reduce((sum, item) => sum + Number(item.amount), 0)
  return {
    receipt,
    items: itemsWithPortions,
    opt_outs: optedOutIds,
    split: {
      ...split,
      participant_totals: split.participants.map((row) => ({
        participant_id: row.participant_id,
        amount: row.total,
      })),
      unassigned: split.unassigned_pool,
      shared: split.shared_pool,
      adjustments,
      total: split.items_total,
    },
  }
}

/**
 * @param {{signal?: AbortSignal}|undefined} options
 */
function checkAbort(options) {
  if (options?.signal?.aborted) {
    throw new RepositoryError('Request aborted', { code: 'aborted' })
  }
}

/** @type {Promise<any>|null} */
let refreshInFlight = null
/** @type {{at: number, payload: any}|null} */
let lastRefresh = null

/**
 * Debounced push after a local mutation. Recurring creates request an
 * immediate push because the server owns frame materialization.
 *
 * @param {string} groupId
 * @param {{immediate?: boolean}} [options]
 */
async function flushGroup(groupId, options = {}) {
  if (!isOnline()) {
    scheduleSync()
    return
  }
  if (!options.immediate) {
    scheduleSync()
    return
  }
  try {
    await pushPending({ groupId })
  } catch {
    scheduleSync()
  }
}

const auth = {
  async me(options = {}) {
    return run(async () => {
      await ready()
      try {
        const payload = await onlineRepository.auth.me(options)
        if (payload) {
          await cacheUser(payload)
          await setMetadata('auth_providers', onlineRepository.auth.providers())
          return payload
        }
        // `/me` without an access token is expected on a reload: the caller
        // immediately tries refresh. Return null without clearing the cache;
        // refresh decides whether the session is really absent.
        return null
      } catch (error) {
        const code = error && typeof error === 'object' && 'code' in error ? error.code : 'network'
        if (code === 'aborted') throw error
        // Only transport/server failures may use the offline cache. An auth
        // rejection must not resurrect the previous account.
        if (['network', 'server', 'rate_limited'].includes(code)) return cachedUser()
        return null
      }
    })
  },
  async refresh(options = {}) {
    return run(async () => {
      await ready()
      // The shell can mount twice in React StrictMode; sharing one refresh
      // keeps the rotating cookie from being replayed inside the same tab.
      if (lastRefresh && Date.now() - lastRefresh.at < 2000) return lastRefresh.payload
      if (refreshInFlight) return refreshInFlight
      refreshInFlight = (async () => {
        const payload = await onlineRepository.auth.refresh(options)
        if (payload?.user) {
          await cacheUser(payload.user)
          lastRefresh = { at: Date.now(), payload }
          scheduleSync({ delay: 0 })
        } else {
          // Refresh is the authoritative session check: no user means the
          // browser is signed out, so clear the previous account's cache.
          await cacheUser(null)
        }
        return payload
      })().finally(() => {
        refreshInFlight = null
      })
      return refreshInFlight
    })
  },
  async logout(options = {}) {
    /** @type {unknown} */
    let failure = null
    try {
      await run(async () => {
        await onlineRepository.auth.logout(options)
      })
    } catch (error) {
      failure = error
    } finally {
      // Clear local account data even when the server logout request fails;
      // the user asked to sign out of this browser.
      await cacheUser(null)
    }
    if (failure) throw failure
  },
  startOAuth(provider, returnTo = '/groups') {
    return onlineRepository.auth.startOAuth(provider, returnTo)
  },
  providers() {
    return onlineRepository.auth.providers()
  },
}

const groups = {
  async list(options = {}, read = {}) {
    return run(async () => {
      checkAbort(read)
      await ready()
      let groupsList = await cachedGroups(options.ids || [])
      if (isOnline()) {
        try {
          // `groups.sync` also claims requested capability groups for the
          // current account and returns the complete membership list.
          await groups.sync({ groupIds: options.ids || [] }, read)
          groupsList = await cachedGroups(options.ids || [])
        } catch (error) {
          if (error && typeof error === 'object' && 'code' in error && error.code === 'aborted') {
            throw error
          }
          // Offline or server unavailable: the cache is authoritative.
        }
      }
      if (Array.isArray(options.ids)) {
        const requested = new Set(options.ids)
        groupsList = groupsList.filter((group) => requested.has(group.id))
      }
      const filtered = filterGroupStatus(groupsList, options.status || 'all')
      const limit = Math.min(200, Math.max(1, Number(options.limit || 50)))
      const offset = Math.max(0, Number(options.offset || 0))
      return {
        items: filtered.slice(offset, offset + limit),
        total: filtered.length,
        limit,
        offset,
      }
    })
  },
  async get(groupId, _options = {}) {
    return run(async () => {
      checkAbort(_options)
      const group = await ensureGroup(groupId)
      if (!group) return null
      const composed = await composeCachedGroup(group)
      const user = await cachedUser()
      if (user) void recordAccessDebounced(groupId)
      return composed
    })
  },
  async details(groupId, _options = {}) {
    return run(async () => {
      checkAbort(_options)
      const group = await requireGroup(groupId)
      const expenses = await readExpenses(groupId, await liveExpenses(groupId))
      /** @type {string[]} */
      const withExpenses = []
      const seen = new Set()
      for (const expense of expenses) {
        const candidates = [expense.paid_by_id, ...(expense.paid_for || []).map((row) => row.participant_id)]
        for (const participantId of candidates) {
          if (!seen.has(participantId)) {
            seen.add(participantId)
            withExpenses.push(participantId)
          }
        }
      }
      const details = group.participants.filter((participant) =>
        withExpenses.includes(participant.id),
      )
      return {
        group: await composeCachedGroup(group),
        participants_with_expenses: withExpenses,
        participants_with_expense_details: details,
        participantsWithExpenses: withExpenses,
      }
    })
  },
  async create(input, options = {}) {
    return run(async () => {
      checkAbort(options)
      await ready()
      const user = await cachedUser()
      if (!isOnline() && !canCreateFromCache(user)) {
        throw new RepositoryError('Your tier cannot create groups offline', {
          code: 'forbidden',
          status: 403,
        })
      }
      const timestamp = nowIso()
      const groupId = newId('grp')
      const participants = (input.participants || []).map((participant, index) => ({
        id: participant.id || newId('par'),
        name: participant.name,
        group_id: groupId,
        updated_at: timestamp,
        version: 1,
        deleted_at: null,
        position: index,
        pending: true,
      }))
      const record = {
        id: groupId,
        name: input.name,
        information: input.information ?? null,
        currency: input.currency || '$',
        currency_code: input.currencyCode || input.currency_code || null,
        created_at: timestamp,
        updated_at: timestamp,
        version: 1,
        deleted_at: null,
        pending: true,
      }
      const payload = {
        name: record.name,
        information: record.information,
        currency: record.currency,
        currency_code: record.currency_code,
        participants: participants.map((participant) => ({
          id: participant.id,
          name: participant.name,
        })),
      }
      await db.transaction(
        'rw',
        [db.groups, db.participants, db.outbox, db.userGroups, db.metadata],
        async () => {
          await db.groups.put(record)
          await db.participants.bulkPut(participants)
          await enqueue({
            op_id: newId('op'),
            group_id: groupId,
            entity_type: 'group',
            entity_id: groupId,
            op_type: 'create',
            payload,
          })
          if (user) {
            await db.userGroups.put({
              id: `${user.id}:${groupId}`,
              user_id: user.id,
              group_id: groupId,
              is_starred: false,
              is_archived: false,
              created_at: timestamp,
              updated_at: timestamp,
              version: 1,
              deleted_at: null,
            })
          }
          await rememberRecent(record)
        },
      )
      await flushGroup(groupId)
      const stored = await readGroup(groupId)
      return composeCachedGroup(stored)
    })
  },
  async update(groupId, input, options = {}) {
    return run(async () => {
      checkAbort(options)
      const group = await requireGroup(groupId)
      const timestamp = nowIso()
      const fields = {
        ...(input.name !== undefined ? { name: input.name } : {}),
        ...(input.information !== undefined ? { information: input.information } : {}),
        ...(input.currency !== undefined ? { currency: input.currency } : {}),
        ...(input.currencyCode !== undefined || input.currency_code !== undefined
          ? { currency_code: input.currencyCode ?? input.currency_code ?? null }
          : {}),
      }
      const participants = Array.isArray(input.participants) ? input.participants : null
      const existing = group.participants || []
      const operations = []
      const nextParticipants = []

      if (Object.keys(fields).length) {
        operations.push({
          op_id: newId('op'),
          group_id: groupId,
          entity_type: 'group',
          entity_id: groupId,
          op_type: 'update',
          base_version: Number(group.version || 0),
          payload: fields,
        })
      }

      if (participants) {
        const seen = new Set()
        for (const [index, participant] of participants.entries()) {
          const current = participant.id ? existing.find((row) => row.id === participant.id) : null
          if (participant.id && current) {
            seen.add(participant.id)
            const changed = current.name !== participant.name
            nextParticipants.push({
              ...current,
              name: participant.name,
              ...(changed
                ? {
                    updated_at: timestamp,
                    version: Number(current.version || 0) + 1,
                  }
                : {}),
              pending: Boolean(current.pending) || changed,
            })
            if (changed) {
              operations.push({
                op_id: newId('op'),
                group_id: groupId,
                entity_type: 'participant',
                entity_id: participant.id,
                op_type: 'update',
                base_version: Number(current.version || 0),
                payload: { name: participant.name },
              })
            }
          } else {
            const participantId = participant.id || newId('par')
            seen.add(participantId)
            const created = {
              id: participantId,
              name: participant.name,
              group_id: groupId,
              updated_at: timestamp,
              version: 1,
              deleted_at: null,
              position: index,
              pending: true,
            }
            nextParticipants.push(created)
            operations.push({
              op_id: newId('op'),
              group_id: groupId,
              entity_type: 'participant',
              entity_id: participantId,
              op_type: 'create',
              payload: { name: participant.name },
            })
          }
        }
        for (const current of existing) {
          if (seen.has(current.id)) continue
          nextParticipants.push({
            ...current,
            deleted_at: timestamp,
            updated_at: timestamp,
            version: Number(current.version || 0) + 1,
            pending: true,
          })
          operations.push({
            op_id: newId('op'),
            group_id: groupId,
            entity_type: 'participant',
            entity_id: current.id,
            op_type: 'delete',
            base_version: Number(current.version || 0),
            payload: {},
          })
        }
      }

      await db.transaction(
        'rw',
        [db.groups, db.participants, db.outbox],
        async () => {
          await db.groups.put({
            ...group,
            ...fields,
            participants: undefined,
            updated_at: timestamp,
            version: Number(group.version || 0) + (Object.keys(fields).length ? 1 : 0),
            pending: true,
          })
          if (participants) {
            await db.participants.where('group_id').equals(groupId).delete()
            await db.participants.bulkPut(
              nextParticipants.map((participant, index) => ({
                ...participant,
                position: index,
              })),
            )
          }
          for (const operation of operations) await enqueue(operation)
        },
      )
      await flushGroup(groupId)
      return composeCachedGroup(await readGroup(groupId))
    })
  },
  async removeMembership(groupId, options = {}) {
    await run(async () => {
      checkAbort(options)
      await ready()
      const user = await cachedUser()
      const membership = user
        ? await db.userGroups.get(`${user.id}:${groupId}`)
        : null
      // Leaving a group (or dismissing a capability URL) must remove the local
      // cache too; otherwise the group stays readable by direct URL.
      await deleteLocalGroup(groupId)
      if (membership) {
        await db.transaction('rw', [db.outbox], async () => {
          await enqueue({
            op_id: newId('op'),
            group_id: groupId,
            entity_type: 'user_group',
            entity_id: groupId,
            op_type: 'delete',
            base_version: Number(membership.version || 0),
            payload: {},
          })
        })
      }
      await flushGroup(groupId)
    })
  },
  async recordAccess(groupId, options = {}) {
    if (!isOnline()) return
    const user = await cachedUser()
    if (!user) return
    await run(async () => {
      await onlineRepository.groups.recordAccess(groupId, options)
    })
  },
  async setStarred(groupId, value, options = {}) {
    return run(async () => {
      checkAbort(options)
      await ready()
      return updateMembership(
        groupId,
        value ? { is_starred: true, is_archived: false } : { is_starred: false },
      )
    })
  },
  async setArchived(groupId, value, options = {}) {
    return run(async () => {
      checkAbort(options)
      await ready()
      return updateMembership(
        groupId,
        value ? { is_archived: true, is_starred: false } : { is_archived: false },
      )
    })
  },
  async sync(input = {}, options = {}) {
    return run(async () => {
      checkAbort(options)
      await ready()
      if (groupsSyncPromise) return groupsSyncPromise
      groupsSyncPromise = (async () => {
        const requested = [...(input.groupIds || [])]
        if (!isOnline()) {
          const localGroups = await cachedGroups(requested)
          return {
            is_authenticated: Boolean(await cachedUser()),
            isAuthenticated: Boolean(await cachedUser()),
            groups: requested.length
              ? localGroups.filter((group) => requested.includes(group.id))
              : [],
            user_groups: await db.userGroups.toArray(),
          }
        }
        try {
          const result = await onlineRepository.groups.sync(
            {
              // Only ids the caller actually asked for. Enumerating every cached
              // group here would grant the next account membership in the
              // previous user's groups.
              groupIds: requested,
              starredGroupIds: input.starredGroupIds || (await getMetadata('starredGroups', [])),
              archivedGroupIds:
                input.archivedGroupIds || (await getMetadata('archivedGroups', [])),
            },
            options,
          )
          await cacheSyncResult(result)
          // The response is the complete membership list for an authenticated
          // account. Prefetch all of it so every visible group becomes fully
          // readable, not just the five most recent ids.
          const returned = (Array.isArray(result?.groups) ? result.groups : []).map(
            (group) => group.id,
          )
          void prefetchGroups(returned)
          return result
        } catch (error) {
          if (error && typeof error === 'object' && 'code' in error && error.code === 'aborted') {
            throw error
          }
          const localGroups = await cachedGroups(requested)
          return {
            is_authenticated: Boolean(await cachedUser()),
            isAuthenticated: Boolean(await cachedUser()),
            groups: requested.length
              ? localGroups.filter((group) => requested.includes(group.id))
              : [],
            user_groups: await db.userGroups.toArray(),
          }
        }
      })().finally(() => {
        groupsSyncPromise = null
      })
      return groupsSyncPromise
    })
  },
}

/**
 * @param {string} groupId
 * @param {{is_starred?: boolean, is_archived?: boolean}} patch
 */
async function updateMembership(groupId, patch) {
  const user = await cachedUser()
  const metadataStarred = new Set(await getMetadata('starredGroups', []))
  const metadataArchived = new Set(await getMetadata('archivedGroups', []))
  if (patch.is_starred === true) {
    metadataStarred.add(groupId)
    metadataArchived.delete(groupId)
  } else if (patch.is_starred === false) {
    metadataStarred.delete(groupId)
  }
  if (patch.is_archived === true) {
    metadataArchived.add(groupId)
    metadataStarred.delete(groupId)
  } else if (patch.is_archived === false) {
    metadataArchived.delete(groupId)
  }

  let membership = user ? await db.userGroups.get(`${user.id}:${groupId}`) : null
  const timestamp = nowIso()
  const definedPatch = Object.fromEntries(
    Object.entries(patch).filter(([, value]) => value !== undefined),
  )
  const next = {
    id: membership?.id || `${user?.id || 'guest'}:${groupId}`,
    user_id: user?.id || 'guest',
    group_id: groupId,
    is_starred: membership?.is_starred ?? false,
    is_archived: membership?.is_archived ?? false,
    created_at: membership?.created_at || timestamp,
    updated_at: timestamp,
    version: Number(membership?.version || 0) + (membership ? 1 : 0),
    deleted_at: null,
    ...definedPatch,
  }

  await db.transaction('rw', [db.userGroups, db.outbox, db.metadata], async () => {
    if (user) await db.userGroups.put(next)
    await db.metadata.put({
      key: 'starredGroups',
      value: [...metadataStarred],
      updated_at: timestamp,
    })
    await db.metadata.put({
      key: 'archivedGroups',
      value: [...metadataArchived],
      updated_at: timestamp,
    })
    if (user) {
      await enqueue({
        op_id: newId('op'),
        group_id: groupId,
        entity_type: 'user_group',
        entity_id: groupId,
        op_type: membership ? 'update' : 'create',
        ...(membership ? { base_version: Number(membership.version || 0) } : {}),
        payload: { is_starred: next.is_starred, is_archived: next.is_archived },
      })
    }
  })
  await flushGroup(groupId)
  return next
}

const participants = {
  async list(groupId, options = {}) {
    return run(async () => {
      checkAbort(options)
      await requireGroup(groupId)
      return liveParticipants(groupId)
    })
  },
  async upsert(groupId, input, options = {}) {
    return run(async () => {
      checkAbort(options)
      const group = await requireGroup(groupId)
      const timestamp = nowIso()
      let participant
      if (input?.id) {
        const current = (group.participants || []).find((row) => row.id === input.id)
        if (!current) {
          throw new RepositoryError('Participant not found', { code: 'not_found', status: 404 })
        }
        participant = { ...current, name: input.name, updated_at: timestamp, version: Number(current.version || 0) + 1 }
        await db.transaction('rw', [db.participants, db.outbox], async () => {
          await db.participants.put({ ...participant, pending: true })
          await enqueue({
            op_id: newId('op'),
            group_id: groupId,
            entity_type: 'participant',
            entity_id: participant.id,
            op_type: 'update',
            base_version: Number(current.version || 0),
            payload: { name: input.name },
          })
        })
      } else {
        const id = newId('par')
        participant = {
          id,
          name: input.name,
          group_id: groupId,
          updated_at: timestamp,
          version: 1,
          deleted_at: null,
          position: (group.participants || []).length,
          pending: true,
        }
        await db.transaction('rw', [db.participants, db.outbox], async () => {
          await db.participants.put(participant)
          await enqueue({
            op_id: newId('op'),
            group_id: groupId,
            entity_type: 'participant',
            entity_id: id,
            op_type: 'create',
            payload: { name: input.name },
          })
        })
      }
      await flushGroup(groupId)
      return participant
    })
  },
  async remove(groupId, id, options = {}) {
    await run(async () => {
      checkAbort(options)
      const participant = await db.participants.get(id)
      if (!participant || participant.group_id !== groupId) {
        throw new RepositoryError('Participant not found', { code: 'not_found', status: 404 })
      }
      const timestamp = nowIso()
      await db.transaction('rw', [db.participants, db.outbox], async () => {
        await db.participants.put({
          ...participant,
          deleted_at: timestamp,
          updated_at: timestamp,
          version: Number(participant.version || 0) + 1,
          pending: true,
        })
        await enqueue({
          op_id: newId('op'),
          group_id: groupId,
          entity_type: 'participant',
          entity_id: id,
          op_type: 'delete',
          base_version: Number(participant.version || 0),
          payload: {},
        })
      })
      await flushGroup(groupId)
    })
  },
}

const categories = {
  async list(options = {}) {
    return run(async () => {
      checkAbort(options)
      await ready()
      if (isOnline()) {
        try {
          const payload = await onlineRepository.categories.list(options)
          const items = payload?.items || payload || []
          if (items.length) await db.categories.bulkPut(items)
          return payload?.items ? payload : { items, total: items.length, limit: 200, offset: 0 }
        } catch (error) {
          if (error && typeof error === 'object' && 'code' in error && error.code === 'aborted') {
            throw error
          }
        }
      }
      let items = await db.categories.toArray()
      if (!items.length) {
        items = DEFAULT_CATEGORIES
        await db.categories.bulkPut(items)
      }
      items.sort((first, second) => Number(first.id) - Number(second.id))
      return { items, total: items.length, limit: 200, offset: 0 }
    })
  },
  async infer(title, options = {}) {
    return run(async () => {
      if (!isOnline()) {
        throw new RepositoryError('Category inference is available when online', {
          code: 'offline_unsupported',
        })
      }
      return onlineRepository.categories.infer(title, options)
    })
  },
}

const expenses = {
  async list(groupId, options = {}, _read = {}) {
    return run(async () => {
      checkAbort(_read)
      await requireGroup(groupId)
      const queryText = String(options.q || '').trim().toLowerCase()
      let rows = await liveExpenses(groupId)
      if (options.from || options.to) {
        rows = rows.filter((row) => {
          const value = String(row.expense_date).slice(0, 10)
          if (options.from && value < options.from) return false
          if (options.to && value > options.to) return false
          return true
        })
      }
      if (queryText) {
        rows = rows.filter((row) => String(row.title || '').toLowerCase().includes(queryText))
      }
      const total = rows.length
      const limit = Math.min(200, Math.max(1, Number(options.limit || 50)))
      const offset = Math.max(0, Number(options.offset || 0))
      const items = await readExpenses(groupId, rows.slice(offset, offset + limit))
      return { items, total, limit, offset }
    })
  },
  async get(groupId, expenseId, _options = {}) {
    return run(async () => {
      checkAbort(_options)
      await requireGroup(groupId)
      const row = await db.expenses.get(expenseId)
      if (!row || row.group_id !== groupId || row.deleted_at) return null
      return readExpense(row)
    })
  },
  async create(groupId, input, options = {}) {
    return run(async () => {
      checkAbort(options)
      await requireGroup(groupId)
      const timestamp = nowIso()
      const id = input.id || newId('exp')
      const splitMode = input.split_mode || 'EVENLY'
      const amount = Number(input.amount)
      const normalizedPaidFor = normalizePaidFor(input.paid_for, splitMode, amount)
      const record = localExpenseRecord({
        id,
        group_id: groupId,
        expense_date: String(input.expense_date).slice(0, 10),
        title: input.title,
        category_id: Number(input.category_id || 0),
        amount,
        original_amount: input.original_amount ?? null,
        original_currency: input.original_currency ?? null,
        conversion_rate: input.conversion_rate ?? null,
        paid_by_id: input.paid_by_id,
        is_reimbursement: Boolean(input.is_reimbursement),
        split_mode: splitMode,
        notes: input.notes ?? null,
        recurrence_rule: input.recurrence_rule || 'NONE',
        is_recurring_head: (input.recurrence_rule || 'NONE') !== 'NONE',
        created_at: timestamp,
        updated_at: timestamp,
        version: 1,
        deleted_at: null,
      })
      const paidFor = normalizedPaidFor.map((row) => ({ ...row, expense_id: id }))
      const payload = {
        expense_date: record.expense_date,
        title: record.title,
        category_id: record.category_id,
        amount: record.amount,
        original_amount: record.original_amount,
        original_currency: record.original_currency,
        conversion_rate: record.conversion_rate,
        paid_by_id: record.paid_by_id,
        is_reimbursement: record.is_reimbursement,
        split_mode: record.split_mode,
        notes: record.notes,
        recurrence_rule: record.recurrence_rule,
        paid_for: normalizedPaidFor,
        ...(input.participant_id ? { participant_id: input.participant_id } : {}),
      }
      await db.transaction('rw', [db.expenses, db.paidFor, db.outbox], async () => {
        await db.expenses.put(record)
        if (paidFor.length) await db.paidFor.bulkPut(paidFor)
        await enqueue({
          op_id: newId('op'),
          group_id: groupId,
          entity_type: 'expense',
          entity_id: id,
          op_type: 'create',
          payload,
        })
      })
      await flushGroup(groupId, {
        immediate: isOnline() && record.recurrence_rule !== 'NONE',
      })
      if (isOnline() && record.recurrence_rule !== 'NONE') {
        // The server owns recurrence materialization; refresh the cached frames
        // so a backdated recurring expense shows the same occurrences offline.
        await bootstrapGroup(groupId, { updateCursor: false }).catch(() => {})
      }
      return readExpense((await db.expenses.get(id)) || record)
    })
  },
  async update(groupId, expenseId, input, options = {}) {
    return run(async () => {
      checkAbort(options)
      await requireGroup(groupId)
      const current = await db.expenses.get(expenseId)
      if (!current || current.group_id !== groupId || current.deleted_at) {
        throw new RepositoryError('Expense not found', { code: 'not_found', status: 404 })
      }
      const timestamp = nowIso()
      const allowed = [
        'expense_date',
        'title',
        'category_id',
        'amount',
        'original_amount',
        'original_currency',
        'conversion_rate',
        'paid_by_id',
        'is_reimbursement',
        'split_mode',
        'notes',
        'recurrence_rule',
      ]
      const payload = {}
      for (const key of allowed) {
        if (input[key] !== undefined) payload[key] = input[key]
      }
      if (payload.expense_date) payload.expense_date = String(payload.expense_date).slice(0, 10)
      let paidFor = null
      if (Array.isArray(input.paid_for)) {
        paidFor = normalizePaidFor(
          input.paid_for,
          payload.split_mode || current.split_mode || 'EVENLY',
          Number(payload.amount ?? current.amount),
        )
        payload.paid_for = paidFor
      }
      if (input.participant_id) payload.participant_id = input.participant_id
      const baseVersion = Number(
        input.base_version ?? options.base_version ?? current.version ?? 0,
      )
      const next = {
        ...current,
        ...payload,
        ...(payload.recurrence_rule !== undefined
          ? { is_recurring_head: payload.recurrence_rule !== 'NONE' }
          : {}),
        paid_for: undefined,
        updated_at: timestamp,
        version: Number(current.version || 0) + 1,
        pending: true,
      }
      await db.transaction('rw', [db.expenses, db.paidFor, db.outbox], async () => {
        await db.expenses.put(next)
        if (paidFor) {
          await db.paidFor.where('expense_id').equals(expenseId).delete()
          if (paidFor.length) {
            await db.paidFor.bulkPut(paidFor.map((row) => ({ ...row, expense_id: expenseId })))
          }
        }
        await enqueue({
          op_id: newId('op'),
          group_id: groupId,
          entity_type: 'expense',
          entity_id: expenseId,
          op_type: 'update',
          base_version: baseVersion,
          payload,
        })
      })
      await flushGroup(groupId)
      return readExpense((await db.expenses.get(expenseId)) || next)
    })
  },
  async remove(groupId, expenseId, options = {}) {
    await run(async () => {
      checkAbort(options)
      await requireGroup(groupId)
      const current = await db.expenses.get(expenseId)
      if (!current || current.group_id !== groupId || current.deleted_at) {
        throw new RepositoryError('Expense not found', { code: 'not_found', status: 404 })
      }
      const timestamp = nowIso()
      const baseVersion = Number(options.base_version ?? current.version ?? 0)
      await db.transaction('rw', [db.expenses, db.outbox], async () => {
        await db.expenses.put({
          ...current,
          deleted_at: timestamp,
          updated_at: timestamp,
          version: Number(current.version || 0) + 1,
          pending: true,
        })
        await enqueue({
          op_id: newId('op'),
          group_id: groupId,
          entity_type: 'expense',
          entity_id: expenseId,
          op_type: 'delete',
          base_version: baseVersion,
          payload: {},
        })
      })
      await flushGroup(groupId)
    })
  },
}

const balances = {
  async list(groupId, _options = {}) {
    return run(async () => {
      checkAbort(_options)
      await requireGroup(groupId)
      const expenses = await readExpenses(groupId, await liveExpenses(groupId))
      const balances = getBalances(expenses)
      const reimbursements = getSuggestedReimbursements(balances)
      const publicBalances = getPublicBalances(reimbursements)
      return {
        balances: [...publicBalances.entries()]
          .sort(([first], [second]) => (first < second ? -1 : 1))
          .map(([participantId, values]) => ({
            participant_id: participantId,
            total: values.total,
            paid: values.paid,
            paid_for: values.paidFor,
          })),
        reimbursements,
      }
    })
  },
  async forUser(entries, options = {}) {
    return run(async () => {
      checkAbort(options)
      const activeEntries = entries || []
      const groupIds = [...new Set(activeEntries.map((entry) => entry.group_id))]
      if (!groupIds.length) return []
      const [groups, participants, expenseRows, user, memberships] = await Promise.all([
        db.groups.where('id').anyOf(groupIds).toArray(),
        db.participants.where('group_id').anyOf(groupIds).toArray(),
        db.expenses.where('group_id').anyOf(groupIds).toArray(),
        cachedUser(),
        db.userGroups.where('group_id').anyOf(groupIds).toArray(),
      ])
      const groupsById = new Map(groups.map((group) => [group.id, group]))
      const participantsById = new Map(participants.map((row) => [row.id, row]))
      const membershipKeys = new Set(
        memberships.map((row) => `${row.user_id}:${row.group_id}`),
      )
      const liveByGroup = new Map()
      for (const row of expenseRows) {
        if (row.deleted_at) continue
        const list = liveByGroup.get(row.group_id) || []
        list.push(row)
        liveByGroup.set(row.group_id, list)
      }
      const balanceByGroup = new Map()
      for (const groupId of groupIds) {
        balanceByGroup.set(
          groupId,
          getBalances(await readExpenses(groupId, liveByGroup.get(groupId) || [])),
        )
      }
      const items = []
      for (const entry of activeEntries) {
        const group = groupsById.get(entry.group_id)
        if (!group || group.deleted_at) continue
        if (user && !membershipKeys.has(`${user.id}:${entry.group_id}`)) continue
        const participant = participantsById.get(entry.participant_id)
        if (!participant || participant.group_id !== entry.group_id || participant.deleted_at) {
          continue
        }
        const balanceMap = balanceByGroup.get(entry.group_id) || new Map()
        items.push({
          group_id: group.id,
          group_name: group.name,
          currency: group.currency,
          currency_code: group.currency_code,
          participant_id: participant.id,
          participant_name: participant.name,
          amount: Number(balanceMap.get(entry.participant_id)?.total || 0),
        })
      }
      return items
    })
  },
}

const stats = {
  async overview(groupId, options = {}, _read = {}) {
    return run(async () => {
      checkAbort(_read)
      const group = await requireGroup(groupId)
      const allExpenses = await readExpenses(groupId, await liveExpenses(groupId))
      const expenses = filterExpensesByDateRange(allExpenses, options.from, options.to)
      const participants = group.participants.map((participant) => ({
        id: participant.id,
        name: participant.name,
      }))
      const participantRows = getSpendingByParticipant(participants, expenses)
      // Mirror the server: recurring statistics come from the active head of
      // each series, never from every materialized frame and never from the
      // date-filtered range.
      const recurring = getRecurringSpending(
        allExpenses
          .filter(
            (expense) =>
              expense.is_recurring_head === true ||
              (expense.is_recurring_head == null && Boolean(expense.pending)),
          )
          .map((expense) => ({
            amount: expense.amount,
            recurrence_rule: expense.recurrence_rule,
            is_reimbursement: expense.is_reimbursement,
          })),
      )
      const totalGroup = getTotalGroupSpending(expenses)
      const totalPaid =
        options.participant_id != null
          ? getTotalActiveUserPaidFor(options.participant_id, expenses)
          : null
      const totalShare =
        options.participant_id != null
          ? getTotalActiveUserShare(options.participant_id, expenses)
          : null
      const months = getSpendingOverTime(expenses).map((row) => ({
        month: row.month,
        total: row.total,
        period: row.month,
        amount: row.total,
      }))
      const categoryRows = getSpendingByCategory(expenses).map((row) => ({
        category_id: row.categoryId,
        grouping: row.grouping,
        name: row.name,
        amount: row.total,
        total: row.total,
        categoryId: row.categoryId,
      }))
      const participantSpending = participantRows.map((row) => ({
        participant_id: row.participantId,
        name: row.name,
        amount: row.paid,
        paid: row.paid,
        paid_count: row.paidCount,
        share: row.share,
        participantId: row.participantId,
        paidCount: row.paidCount,
      }))
      const summary = getSpendingSummary(expenses)
      const summaryRead = {
        expense_count: summary.expenseCount,
        total_spending: summary.totalSpending,
        average_expense: summary.averageExpense,
        largest_expense: summary.largestExpense,
        first_date: summary.firstDate,
        last_date: summary.lastDate,
        ...summary,
      }
      return {
        range: { from: options.from || null, to: options.to || null },
        total_group_spending: totalGroup,
        total_active_user_share: totalShare,
        total_active_user_paid_for: totalPaid,
        summary: summaryRead,
        spending_over_time: months,
        spending_by_participant: participantSpending,
        spending_by_category: categoryRows,
        recurring: {
          active_count: recurring.count,
          monthly_amount: recurring.estimatedMonthly,
          yearly_amount: recurring.estimatedYearly,
          count: recurring.count,
          estimated_monthly: recurring.estimatedMonthly,
          estimated_yearly: recurring.estimatedYearly,
          by_period: recurring.byPeriod,
          estimatedMonthly: recurring.estimatedMonthly,
          estimatedYearly: recurring.estimatedYearly,
          byPeriod: recurring.byPeriod,
        },
        totalGroupSpendings: totalGroup,
        totalParticipantSpendings: totalPaid,
        totalParticipantShare: totalShare,
        months,
        participants: participantSpending,
        categories: categoryRows,
      }
    })
  },
  async categoryExpenses(groupId, categoryId, options = {}, read = {}) {
    return run(async () => {
      checkAbort(read)
      await requireGroup(groupId)
      const expenses = filterExpensesByDateRange(
        await readExpenses(groupId, await liveExpenses(groupId)),
        options.from,
        options.to,
      )
      return {
        expenses: getExpensesByCategory(expenses, categoryId).map((expense) => ({
          id: expense.id,
          title: expense.title,
          amount: expense.amount,
          expense_date: expense.expense_date,
          created_at: expense.created_at,
        })),
      }
    })
  },
  async monthExpenses(groupId, month, options = {}, read = {}) {
    return run(async () => {
      checkAbort(read)
      await requireGroup(groupId)
      const expenses = filterExpensesByDateRange(
        await readExpenses(groupId, await liveExpenses(groupId)),
        options.from,
        options.to,
      )
      return {
        expenses: getExpensesByMonth(expenses, month).map((expense) => ({
          id: expense.id,
          title: expense.title,
          amount: expense.amount,
          expense_date: expense.expense_date,
          created_at: expense.created_at,
        })),
      }
    })
  },
}

const activities = {
  async list(groupId, options = {}, _read = {}) {
    return run(async () => {
      checkAbort(_read)
      await requireGroup(groupId)
      if (isOnline()) {
        const age = await getMetadata('activities_refreshed_at', {})
        const last = Number(age?.[groupId] || 0)
        if (Date.now() - last > SYNC_INTERVAL) {
          try {
            const payload = await onlineRepository.activities.list(groupId, { limit: 100 })
            const items = payload?.items || []
            await db.activities.where('group_id').equals(groupId).delete()
            if (items.length) await db.activities.bulkPut(items)
            await setMetadata('activities_refreshed_at', { ...age, [groupId]: Date.now() })
          } catch {
            // Fall back to cached activities.
          }
        }
      }
      const rows = (await db.activities.where('group_id').equals(groupId).toArray()).sort(
        (first, second) => {
          if (first.time !== second.time) return first.time < second.time ? 1 : -1
          return first.id < second.id ? 1 : -1
        },
      )
      const cursor = Math.max(0, Number(options.cursor || 0))
      const limit = Math.min(200, Math.max(1, Number(options.limit || 5)))
      const page = rows.slice(cursor, cursor + limit)
      const expenseIds = page.map((row) => row.expense_id).filter(Boolean)
      const expenseRows = expenseIds.length
        ? await db.expenses.where('id').anyOf(expenseIds).toArray()
        : []
      const expensesById = new Map(expenseRows.map((row) => [row.id, row]))
      return {
        items: page.map((row) => {
          const expense = row.expense_id ? expensesById.get(row.expense_id) : null
          return {
            ...row,
            expense:
              expense && !expense.deleted_at
                ? {
                    id: expense.id,
                    title: expense.title,
                    amount: expense.amount,
                    expense_date: String(expense.expense_date).slice(0, 10),
                  }
                : null,
          }
        }),
        next_cursor: String(cursor + limit),
        has_more: cursor + limit < rows.length,
        total: rows.length,
        limit,
        offset: cursor,
      }
    })
  },
}

const receipts = {
  async get(groupId, options = {}, _read = {}) {
    return run(async () => {
      checkAbort(_read)
      await requireGroup(groupId)
      let receipt = null
      if (options.receipt_id) receipt = await db.receipts.get(options.receipt_id)
      else if (options.expense_id) {
        receipt = await db.receipts.where('expense_id').equals(options.expense_id).first()
      }
      if (!receipt || receipt.group_id !== groupId || receipt.deleted_at) return null
      const group = await requireGroup(groupId)
      return receiptState(receipt, group.participants)
    })
  },
  async upload(groupId, file, options = {}) {
    return run(async () => {
      if (!isOnline()) {
        throw new RepositoryError('Receipt uploads are queued for later', {
          code: 'offline_unsupported',
        })
      }
      const result = await onlineRepository.receipts.upload(groupId, file, options)
      return result
    })
  },
  async extractTotal(groupId, input, options = {}) {
    return run(async () => {
      if (!isOnline()) {
        throw new RepositoryError('Receipt extraction is available when online', {
          code: 'offline_unsupported',
        })
      }
      const result = await onlineRepository.receipts.extractTotal(groupId, input, options)
      await refreshReceiptFromServer(groupId, result)
      return result
    })
  },
  async extractItems(groupId, input, options = {}) {
    return run(async () => {
      if (!isOnline()) {
        throw new RepositoryError('Receipt extraction is available when online', {
          code: 'offline_unsupported',
        })
      }
      const result = await onlineRepository.receipts.extractItems(groupId, input, options)
      await refreshReceiptFromServer(groupId, result)
      return result
    })
  },
  async addItem(groupId, receiptId, input, options = {}) {
    return mutateReceipt(groupId, receiptId, 'receipt_item', 'create', input, options)
  },
  async updateItem(groupId, receiptId, itemId, input, options = {}) {
    return mutateReceipt(groupId, receiptId, 'receipt_item', 'update', input, options, itemId)
  },
  async deleteItem(groupId, receiptId, itemId, options = {}) {
    return mutateReceipt(groupId, receiptId, 'receipt_item', 'delete', {}, options, itemId)
  },
  async setPortions(groupId, receiptId, itemId, portions, options = {}) {
    return mutateReceipt(
      groupId,
      receiptId,
      'receipt_portion',
      'update',
      { portions },
      options,
      itemId,
    )
  },
  async setOptOut(groupId, receiptId, participantId, value, options = {}) {
    return mutateReceipt(
      groupId,
      receiptId,
      'receipt_opt_out',
      value ? 'create' : 'delete',
      { participant_id: participantId, opted_out: value },
      options,
      participantId,
    )
  },
  async apply(groupId, receiptId, input, options = {}) {
    return run(async () => {
      if (!isOnline()) {
        throw new RepositoryError('Applying a receipt requires a connection', {
          code: 'offline_unsupported',
        })
      }
      const result = await onlineRepository.receipts.apply(groupId, receiptId, input, options)
      await refreshReceiptFromServer(groupId, result)
      return result
    })
  },
  async link(groupId, receiptId, expenseId, options = {}) {
    return run(async () => {
      if (!isOnline()) {
        throw new RepositoryError('Linking a receipt requires a connection', {
          code: 'offline_unsupported',
        })
      }
      const result = await onlineRepository.receipts.link(groupId, receiptId, expenseId, options)
      await refreshReceiptFromServer(groupId, result)
      return result
    })
  },
}

/**
 * @param {string} groupId
 * @param {any} payload
 */
async function refreshReceiptFromServer(groupId, payload) {
  const receipt = payload?.receipt
  if (receipt?.id) {
    await db.receipts.put(receipt)
    const items = payload.items || []
    for (const item of items) {
      await db.receiptItems.put(item)
      await db.receiptPortions.where('item_id').equals(item.id).delete()
      if (item.portions?.length) {
        await db.receiptPortions.bulkPut(item.portions)
      }
    }
    const optOuts = payload.opt_outs || []
    await db.receiptOptOuts.where('receipt_id').equals(receipt.id).delete()
    for (const participantId of optOuts) {
      await db.receiptOptOuts.put({
        id: `${receipt.id}:${participantId}`,
        receipt_id: receipt.id,
        participant_id: participantId,
        updated_at: nowIso(),
        version: 1,
        deleted_at: null,
      })
    }
  }
  if (groupId) await bootstrapGroup(groupId, { updateCursor: false }).catch(() => {})
}

/**
 * Apply a receipt item mutation locally and queue a REST transport operation.
 *
 * @param {string} groupId
 * @param {string} receiptId
 * @param {string} entityType
 * @param {'create'|'update'|'delete'} opType
 * @param {any} input
 * @param {any} options
 * @param {string} [entityId]
 */
async function mutateReceipt(groupId, receiptId, entityType, opType, input, options, entityId) {
  return run(async () => {
    checkAbort(options)
    await requireGroup(groupId)
    const receipt = await db.receipts.get(receiptId)
    if (!receipt || receipt.group_id !== groupId || receipt.deleted_at) {
      throw new RepositoryError('Receipt not found', { code: 'not_found', status: 404 })
    }
    const timestamp = nowIso()
    let targetId = entityId || newId('ri')

    await db.transaction(
      'rw',
      [db.receiptItems, db.receiptPortions, db.receiptOptOuts, db.outbox],
      async () => {
        if (entityType === 'receipt_item') {
          if (opType === 'create') {
            const items = await db.receiptItems.where('receipt_id').equals(receiptId).toArray()
            await db.receiptItems.put({
              id: targetId,
              receipt_id: receiptId,
              name: input.name,
              quantity_milli: Number(input.quantity_milli || 1000),
              unit_price: input.unit_price ?? null,
              amount: Number(input.amount),
              is_shared: Boolean(input.is_shared),
              is_adjustment: false,
              position: items.length,
              created_at: timestamp,
              updated_at: timestamp,
              version: 1,
              deleted_at: null,
              pending: true,
            })
          } else if (opType === 'update') {
            const item = await db.receiptItems.get(targetId)
            if (!item) throw new RepositoryError('Item not found', { code: 'not_found', status: 404 })
            await db.receiptItems.put({
              ...item,
              ...input,
              updated_at: timestamp,
              version: Number(item.version || 0) + 1,
              pending: true,
            })
          } else {
            const item = await db.receiptItems.get(targetId)
            if (item) {
              await db.receiptItems.put({
                ...item,
                deleted_at: timestamp,
                updated_at: timestamp,
                version: Number(item.version || 0) + 1,
                pending: true,
              })
            }
          }
        } else if (entityType === 'receipt_portion') {
          const item = await db.receiptItems.get(entityId)
          if (!item) throw new RepositoryError('Item not found', { code: 'not_found', status: 404 })
          await db.receiptPortions.where('item_id').equals(entityId).delete()
          const rows = (input.portions || []).map((portion, index) => ({
            id: newId('rp'),
            item_id: entityId,
            target: portion.target,
            participant_id: portion.participant_id ?? null,
            quantity_milli: Number(portion.quantity_milli || 0),
            created_at: timestamp,
            updated_at: timestamp,
            version: 1,
            deleted_at: null,
            position: index,
          }))
          if (rows.length) await db.receiptPortions.bulkPut(rows)
          targetId = entityId
        } else if (entityType === 'receipt_opt_out') {
          const existing = await db.receiptOptOuts.get(`${receiptId}:${entityId}`)
          if (opType === 'delete') {
            if (existing) {
              await db.receiptOptOuts.put({
                ...existing,
                deleted_at: timestamp,
                updated_at: timestamp,
              })
            }
          } else {
            await db.receiptOptOuts.put({
              id: `${receiptId}:${entityId}`,
              receipt_id: receiptId,
              participant_id: entityId,
              created_at: existing?.created_at || timestamp,
              updated_at: timestamp,
              version: Number(existing?.version || 0) + 1,
              deleted_at: null,
            })
          }
        }

        await enqueue({
          op_id: newId('op'),
          group_id: groupId,
          entity_type: entityType,
          entity_id: targetId,
          op_type: opType,
          payload:
            entityType === 'receipt_item' && opType === 'create'
              ? { ...input, id: targetId }
              : input,
          transport: 'rest',
          meta: { receipt_id: receiptId, participant_id: entityId, item_id: entityId },
        })
      },
    )
    await flushGroup(groupId)
    const group = await requireGroup(groupId)
    const updatedReceipt = await db.receipts.get(receiptId)
    return receiptState(updatedReceipt, group.participants)
  })
}

const documents = {
  async upload(groupId, expenseId, file, options = {}) {
    return run(async () => {
      if (!isOnline()) {
        throw new RepositoryError('Document uploads are available when online', {
          code: 'offline_unsupported',
        })
      }
      const document = await onlineRepository.documents.upload(groupId, expenseId, file, options)
      await db.documents.put({
        ...document,
        expense_id: expenseId,
        created_at: nowIso(),
      })
      return document
    })
  },
  async remove(groupId, expenseId, documentId, options = {}) {
    await run(async () => {
      if (!isOnline()) {
        throw new RepositoryError('Document removal is available when online', {
          code: 'offline_unsupported',
        })
      }
      await onlineRepository.documents.remove(groupId, expenseId, documentId, options)
      await db.documents.delete(documentId)
    })
  },
}

const exportsRepository = {
  async csv(groupId, options = {}, read = {}) {
    return run(async () => {
      await requireGroup(groupId)
      if (isOnline()) {
        try {
          return await onlineRepository.exports.csv(groupId, options, read)
        } catch (error) {
          if (error && typeof error === 'object' && 'code' in error && error.code === 'aborted') {
            throw error
          }
        }
      }
      return exportExpenses(groupId, 'csv', options)
    })
  },
  async json(groupId, options = {}, read = {}) {
    return run(async () => {
      await requireGroup(groupId)
      if (isOnline()) {
        try {
          return await onlineRepository.exports.json(groupId, options, read)
        } catch (error) {
          if (error && typeof error === 'object' && 'code' in error && error.code === 'aborted') {
            throw error
          }
        }
      }
      return exportExpenses(groupId, 'json', options)
    })
  },
}

/**
 * @param {string} groupId
 * @param {'csv'|'json'} format
 * @param {{from?: string, to?: string}} options
 */
async function exportExpenses(groupId, format, options) {
  const group = await requireGroup(groupId)
  let rows = await readExpenses(groupId, await liveExpenses(groupId))
  if (options.from || options.to) {
    rows = filterExpensesByDateRange(rows, options.from, options.to)
  }
  rows = [...rows].sort((first, second) => {
    const firstDate = String(first.expense_date).slice(0, 10)
    const secondDate = String(second.expense_date).slice(0, 10)
    if (firstDate !== secondDate) return firstDate < secondDate ? -1 : 1
    const firstCreated = String(first.created_at || '')
    const secondCreated = String(second.created_at || '')
    if (firstCreated !== secondCreated) return firstCreated < secondCreated ? -1 : 1
    return first.id < second.id ? -1 : first.id > second.id ? 1 : 0
  })
  const today = new Date().toISOString().slice(0, 10)
  if (format === 'json') {
    const activities = (await db.activities.where('group_id').equals(groupId).toArray()).sort(
      (first, second) => {
        const firstTime = String(first.time || '')
        const secondTime = String(second.time || '')
        if (firstTime !== secondTime) return firstTime < secondTime ? -1 : 1
        return first.id < second.id ? -1 : first.id > second.id ? 1 : 0
      },
    )
    const payload = {
      id: group.id,
      name: group.name,
      information: group.information ?? null,
      currency: group.currency,
      currency_code: group.currency_code ?? null,
      expenses: rows.map(exportJsonExpense),
      participants: group.participants.map((participant) => ({
        id: participant.id,
        name: participant.name,
      })),
      activities: activities.map((activity) => ({
        id: activity.id,
        time: isoZ(activity.time),
        activity_type: activity.activity_type,
        participant_id: activity.participant_id ?? null,
        expense_id: activity.expense_id ?? null,
        data: activity.data ?? null,
      })),
    }
    return {
      filename: `Spliit Export - ${today}.json`,
      content: JSON.stringify(payload),
    }
  }
  const lines = buildCsvExport(group, rows)
  return {
    filename: `Spliit Export - ${group.name} - ${today}.csv`,
    content: '\ufeff' + lines,
  }
}

const CSV_FIELDS = [
  'Date',
  'Description',
  'Category',
  'Currency',
  'Cost',
  'Original cost',
  'Original currency',
  'Conversion rate',
  'Is Reimbursement',
  'Split mode',
]

const SPLIT_MODE_LABELS = {
  EVENLY: 'Evenly',
  BY_SHARES: 'Unevenly \u2013 By shares',
  BY_PERCENTAGE: 'Unevenly \u2013 By percentage',
  BY_AMOUNT: 'Unevenly \u2013 By amount',
}

/**
 * @param {unknown} value
 * @returns {string}
 */
function isoZ(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value.replace('+00:00', 'Z')
  const date = value instanceof Date ? value : new Date(String(value))
  return Number.isNaN(date.getTime()) ? String(value) : date.toISOString()
}

/**
 * @param {unknown} value
 * @returns {string}
 */
function escapeCsvFormula(value) {
  const text = String(value ?? '')
  return /^[=+\-@\t\r]/.test(text) ? `'${text}` : text
}

/**
 * Python's csv module uses minimal quoting. Mirror it so offline exports are
 * byte-identical to the server's.
 *
 * @param {unknown} value
 * @returns {string}
 */
function csvField(value) {
  const text = String(value ?? '')
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

/**
 * @param {any} expense
 * @returns {Map<string, number>}
 */
function exportShares(expense) {
  return getExpenseShares(expense)
}

/**
 * @param {any} expense
 * @returns {any}
 */
function exportJsonExpense(expense) {
  return {
    id: expense.id,
    created_at: isoZ(expense.created_at),
    expense_date: String(expense.expense_date).slice(0, 10),
    title: expense.title,
    category: expense.category
      ? { grouping: expense.category.grouping, name: expense.category.name }
      : null,
    amount: Number(expense.amount),
    original_amount: expense.original_amount ?? null,
    original_currency: expense.original_currency ?? null,
    conversion_rate: expense.conversion_rate ?? null,
    paid_by_id: expense.paid_by_id,
    paid_for: (expense.paid_for || []).map((row) => ({
      participant_id: row.participant_id,
      shares: Number(row.shares),
    })),
    is_reimbursement: Boolean(expense.is_reimbursement),
    split_mode: expense.split_mode,
    recurrence_rule: expense.recurrence_rule,
    notes: expense.notes ?? null,
  }
}

/**
 * @param {any} group
 * @param {any[]} expenses
 * @returns {string}
 */
function buildCsvExport(group, expenses) {
  const participants = group.participants || []
  const header = [
    ...CSV_FIELDS,
    ...participants.map((participant) => escapeCsvFormula(participant.name)),
  ]
  const currencyCode = group.currency_code
  const currencyLabel = currencyCode || group.currency || ''
  const lines = [header.map(csvField).join(',')]
  for (const expense of expenses) {
    const shares = exportShares(expense)
    const row = [
      String(expense.expense_date).slice(0, 10),
      escapeCsvFormula(expense.title || ''),
      escapeCsvFormula(expense.category?.name || ''),
      currencyLabel,
      formatAmountAsDecimal(Number(expense.amount), currencyCode),
      expense.original_amount
        ? formatAmountAsDecimal(Number(expense.original_amount), expense.original_currency)
        : '',
      expense.original_currency ?? '',
      expense.conversion_rate ?? '',
      expense.is_reimbursement ? 'Yes' : 'No',
      SPLIT_MODE_LABELS[expense.split_mode] || String(expense.split_mode || ''),
    ]
    for (const participant of participants) {
      const amount = formatAmountForCsv(
        Number(shares.get(participant.id) || 0),
        currencyCode,
      )
      row.push(
        expense.paid_by_id === participant.id || amount === '0' ? amount : `-${amount}`,
      )
    }
    lines.push(row.map(csvField).join(','))
  }
  return lines.join('\n')
}

const features = {
  async get(options = {}) {
    return run(async () => {
      checkAbort(options)
      await ready()
      if (isOnline()) {
        try {
          const payload = await onlineRepository.features.get(options)
          await setMetadata('features', payload)
          return payload
        } catch (error) {
          if (error && typeof error === 'object' && 'code' in error && error.code === 'aborted') {
            throw error
          }
        }
      }
      return (
        (await getMetadata('features', null)) || {
          receipt_extract: false,
          receipt_items: false,
          category_extract: false,
          expense_documents: false,
        }
      )
    })
  },
}

const admin = {
  async metrics(options = {}) {
    return run(async () => {
      ensureOnline('Admin operations')
      return onlineRepository.admin.metrics(options)
    })
  },
  users: {
    async list(input = {}, options = {}) {
      return run(async () => {
        ensureOnline('Admin operations')
        return onlineRepository.admin.users.list(input, options)
      })
    },
    async preauthorize(input, options = {}) {
      return run(async () => {
        ensureOnline('Admin operations')
        return onlineRepository.admin.users.preauthorize(input, options)
      })
    },
    async setTier(userId, tier, options = {}) {
      return run(async () => {
        ensureOnline('Admin operations')
        return onlineRepository.admin.users.setTier(userId, tier, options)
      })
    },
    async remove(userId, options = {}) {
      return run(async () => {
        ensureOnline('Admin operations')
        return onlineRepository.admin.users.remove(userId, options)
      })
    },
  },
  groups: {
    async list(input = {}, options = {}) {
      return run(async () => {
        ensureOnline('Admin operations')
        return onlineRepository.admin.groups.list(input, options)
      })
    },
    async remove(groupId, options = {}) {
      return run(async () => {
        ensureOnline('Admin operations')
        return onlineRepository.admin.groups.remove(groupId, options)
      })
    },
  },
}

/** @param {string} label */
function ensureOnline(label) {
  if (!isOnline()) {
    throw new RepositoryError(`${label} are available when online`, {
      code: 'offline_unsupported',
    })
  }
}

export const localRepository = {
  auth,
  groups,
  participants,
  categories,
  expenses,
  balances,
  stats,
  activities,
  receipts,
  documents,
  exports: exportsRepository,
  features,
  admin,
}
