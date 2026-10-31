// @ts-nocheck
// Dexie tables are untyped at runtime; the repository contract tests cover shapes.
/**
 * Dexie schema and persistence helpers for the offline-first SPA.
 *
 * Only the repository, outbox, sync and backup modules import this file.
 * Components and hooks go through `services/repository`.
 */

import Dexie from 'dexie'

import {
  DATABASE_SCHEMA_VERSION,
  REQUIRED_INDEXES,
  REQUIRED_TABLES,
  STORES_V2,
  STORES_V4,
} from './db-schema'

export {
  DATABASE_BUILD_CONTRACT,
  DATABASE_SCHEMA_VERSION,
  REQUIRED_INDEXES,
  REQUIRED_TABLES,
  STORES_V2,
  STORES_V4,
} from './db-schema'

/**
 * @typedef {import('dexie').Table<any, string>} EntityTable
 * @typedef {Dexie & {
 *   groups: EntityTable,
 *   participants: EntityTable,
 *   expenses: EntityTable,
 *   paidFor: EntityTable,
 *   activities: EntityTable,
 *   attachments: EntityTable,
 *   attachmentItems: EntityTable,
 *   attachmentPortions: EntityTable,
 *   attachmentOptOuts: EntityTable,
 *   categories: EntityTable,
 *   userGroups: EntityTable,
 *   outbox: EntityTable,
 *   syncState: EntityTable,
 *   conflicts: EntityTable,
 *   blobs: EntityTable,
 *   metadata: EntityTable,
 * }} PysplitDb
 */

const database = new Dexie('pysplit')

database.version(2).stores(STORES_V2)
database.version(DATABASE_SCHEMA_VERSION).stores(STORES_V4)

/** @type {PysplitDb} */
export const db = /** @type {any} */ (database)

/** @param {any} table */
function indexNames(table) {
  return new Set(
    (table?.schema?.indexes || []).map((/** @type {any} */ index) => String(index.name)),
  )
}

/**
 * Open the database and make sure every table (and the indexes the repository
 * queries) the UI needs survived the schema upgrade. This only proves that the
 * code already running can open the current database; it is not a simulation
 * of an incoming build's migration. `verifyIncomingBuildCompatibility()` adds
 * the incoming build's declared contract before an update is activated.
 *
 * @returns {Promise<{version: number, tables: string[]}>}
 */
export async function verifyDatabaseCompatibility() {
  await db.open()
  const byName = new Map(db.tables.map((table) => [table.name, table]))
  const missing = REQUIRED_TABLES.filter((name) => !byName.has(name))
  if (missing.length) {
    throw new Error(`missing Dexie tables: ${missing.join(', ')}`)
  }
  const missingIndexes = []
  for (const [tableName, indexes] of Object.entries(REQUIRED_INDEXES)) {
    const table = byName.get(tableName)
    if (!table) continue
    const actual = indexNames(table)
    for (const index of indexes) {
      if (!actual.has(index)) missingIndexes.push(`${tableName}.${index}`)
    }
  }
  if (missingIndexes.length) {
    throw new Error(`missing Dexie indexes: ${missingIndexes.join(', ')}`)
  }
  return { version: Number(db.verno), tables: [...byName.keys()].sort() }
}

/**
 * Fetch the waiting build's Dexie contract. This file is emitted at build time
 * and is deliberately not precached, so `no-store` reads the newly deployed
 * copy rather than the cache belonging to the running build.
 *
 * @returns {Promise<{schemaVersion: number, requiredTables: string[], requiredIndexes: Record<string, string[]>}>}
 */
export async function fetchIncomingBuildContract() {
  if (typeof fetch !== 'function') throw new Error('Build contract is unavailable')
  const response = await fetch('/pwa-build.json', {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`Build contract is unavailable (${response.status})`)
  const contract = await response.json()
  if (!contract || typeof contract !== 'object') {
    throw new Error('Build contract is invalid')
  }
  return contract
}

/**
 * Compare the waiting build's declared Dexie contract with the open database.
 *
 * This catches a build that would downgrade the schema or drop a table/index
 * the current data depends on. It cannot execute the incoming build's
 * migration; that can only be validated with a staged migration or an update
 * e2e using a deliberately newer schema. See docs/offline-capabilities.md §7.
 *
 * @param {{schemaVersion?: number, requiredTables?: string[], requiredIndexes?: Record<string, string[]>}} contract
 * @returns {Promise<{version: number, incomingVersion: number}>}
 */
export async function verifyIncomingBuildCompatibility(contract) {
  await verifyDatabaseCompatibility()
  const currentVersion = Number(db.verno)
  const incomingVersion = Number(contract?.schemaVersion || 0)
  if (!incomingVersion) throw new Error('Incoming build does not declare a Dexie schema version')
  if (incomingVersion < currentVersion) {
    throw new Error(
      `Incoming build schema v${incomingVersion} is older than local v${currentVersion}`,
    )
  }
  // Only tables this build actually requires matter for an update. A Dexie
  // upgrade may leave obsolete stores from a previous development schema; they
  // are not a reason to reject an otherwise compatible build.
  const currentTables = new Set(
    db.tables.map((table) => table.name).filter((name) => REQUIRED_TABLES.includes(name)),
  )
  const incomingTables = new Set(contract?.requiredTables || [])
  const missingTables = [...currentTables].filter((name) => !incomingTables.has(name))
  if (missingTables.length) {
    throw new Error(`Incoming build drops Dexie tables: ${missingTables.join(', ')}`)
  }
  const incomingIndexes = contract?.requiredIndexes || {}
  const missingIndexes = []
  for (const [tableName, indexes] of Object.entries(REQUIRED_INDEXES)) {
    const declared = new Set(incomingIndexes[tableName] || [])
    for (const index of indexes) {
      if (!declared.has(index)) missingIndexes.push(`${tableName}.${index}`)
    }
  }
  if (missingIndexes.length) {
    throw new Error(`Incoming build drops Dexie indexes: ${missingIndexes.join(', ')}`)
  }
  return { version: currentVersion, incomingVersion }
}

/**
 * @param {string} prefix
 * @returns {string}
 */
export function newId(prefix = 'id') {
  const cryptoApi = globalThis.crypto
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return `${prefix}_${cryptoApi.randomUUID()}`
  }
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

/** @returns {string} */
export function nowIso() {
  return new Date().toISOString()
}

/** @returns {boolean} */
export function isOnline() {
  if (typeof navigator === 'undefined') return true
  return navigator.onLine !== false
}

/** @param {string} scope */
export async function readCursor(scope) {
  const row = await db.syncState.get(scope)
  return Number(row?.cursor || 0)
}

/** @param {string} scope @param {number} cursor */
export async function writeCursor(scope, cursor) {
  await db.syncState.put({ scope, cursor: Number(cursor || 0), updated_at: nowIso() })
}

/** @param {string} key @param {unknown} [fallback] */
export async function getMetadata(key, fallback = null) {
  const row = await db.metadata.get(key)
  return row ? row.value : fallback
}

/** @param {string} key @param {unknown} value */
export async function setMetadata(key, value) {
  await db.metadata.put({ key, value, updated_at: nowIso() })
}

/**
 * @param {string} groupId
 * @returns {Promise<any[]>}
 */
export async function liveParticipants(groupId) {
  const rows = await db.participants.where('group_id').equals(groupId).toArray()
  return rows
    .filter((row) => !row.deleted_at)
    .sort((first, second) => Number(first.position ?? 0) - Number(second.position ?? 0))
}

/**
 * @param {string} groupId
 * @returns {Promise<any|null>}
 */
export async function readGroup(groupId) {
  const group = await db.groups.get(groupId)
  if (!group || group.deleted_at) return null
  return { ...group, participants: await liveParticipants(groupId) }
}

/**
 * @param {string} groupId
 * @returns {Promise<any[]>}
 */
export async function liveExpenses(groupId) {
  const rows = await db.expenses.where('group_id').equals(groupId).toArray()
  return rows
    .filter((row) => !row.deleted_at)
    .sort((first, second) => {
      if (first.expense_date !== second.expense_date) {
        return first.expense_date < second.expense_date ? 1 : -1
      }
      if (first.created_at !== second.created_at) {
        return first.created_at < second.created_at ? 1 : -1
      }
      return first.id < second.id ? -1 : first.id > second.id ? 1 : 0
    })
}

/**
 * Assemble one expense from its Dexie tables.
 *
 * @param {any} expense
 * @returns {Promise<any>}
 */
export async function readExpense(expense) {
  if (!expense) return null
  const [paidFor, attachments] = await Promise.all([
    db.paidFor.where('expense_id').equals(expense.id).toArray(),
    db.attachments.where('expense_id').equals(expense.id).toArray(),
  ])
  const category = await db.categories.get(Number(expense.category_id || 0))
  return {
    ...expense,
    category: category || null,
    paid_for: paidFor
      .filter((row) => !row.deleted_at)
      .sort((first, second) =>
        first.participant_id < second.participant_id
          ? -1
          : first.participant_id > second.participant_id
            ? 1
            : 0,
      )
      .map((row) => ({
        participant_id: row.participant_id,
        shares: row.shares,
        ...(row.amount != null ? { amount: row.amount } : {}),
        ...(row.percentage != null ? { percentage: row.percentage } : {}),
      })),
    attachments: attachments
      .filter((row) => !row.deleted_at)
      .sort((first, second) =>
        String(first.created_at || '') < String(second.created_at || '') ? -1 : 1,
      ),
    pending: Boolean(expense.pending),
  }
}

/**
 * @param {string} groupId
 * @param {any[]} expenses
 * @returns {Promise<any[]>}
 */
export async function readExpenses(groupId, expenses) {
  void groupId
  const categoryRows = await db.categories.toArray()
  const categories = new Map(categoryRows.map((row) => [Number(row.id), row]))
  const ids = expenses.map((row) => row.id)
  const [paidFor, attachments] = await Promise.all([
    ids.length ? db.paidFor.where('expense_id').anyOf(ids).toArray() : [],
    ids.length ? db.attachments.where('expense_id').anyOf(ids).toArray() : [],
  ])
  const paidForByExpense = new Map()
  for (const row of paidFor) {
    if (row.deleted_at) continue
    const list = paidForByExpense.get(row.expense_id) || []
    list.push(row)
    paidForByExpense.set(row.expense_id, list)
  }
  const attachmentsByExpense = new Map()
  for (const row of attachments) {
    if (row.deleted_at || !row.expense_id) continue
    const list = attachmentsByExpense.get(row.expense_id) || []
    list.push(row)
    attachmentsByExpense.set(row.expense_id, list)
  }

  return expenses.map((expense) => ({
    ...expense,
    category: categories.get(Number(expense.category_id || 0)) || null,
    paid_for: (paidForByExpense.get(expense.id) || [])
      .sort((first, second) =>
        first.participant_id < second.participant_id
          ? -1
          : first.participant_id > second.participant_id
            ? 1
            : 0,
      )
      .map((row) => ({ participant_id: row.participant_id, shares: row.shares })),
    attachments: (attachmentsByExpense.get(expense.id) || []).sort((first, second) =>
      String(first.created_at || '') < String(second.created_at || '') ? -1 : 1,
    ),
    pending: Boolean(expense.pending),
  }))
}

/**
 * @param {any} group
 * @param {any|null} membership
 * @param {any[]} participants
 * @returns {any}
 */
export function composeGroup(group, membership, participants) {
  const isStarred = Boolean(membership?.is_starred)
  const isArchived = Boolean(membership?.is_archived)
  return {
    ...group,
    participants,
    participants_count: participants.length,
    user_group: membership
      ? {
          user_id: membership.user_id,
          group_id: membership.group_id,
          is_starred: membership.is_starred,
          is_archived: membership.is_archived,
          created_at: membership.created_at,
          updated_at: membership.updated_at,
          version: membership.version,
        }
      : null,
    is_starred: isStarred,
    is_archived: isArchived,
    isStarred,
    isArchived,
  }
}

/**
 * Collect local rows that still have outbox work so a bootstrap snapshot does
 * not erase edits that have not reached the server yet.
 *
 * @param {string} groupId
 */
async function capturePendingSnapshotState(groupId) {
  const operations = await db.outbox.where('group_id').equals(groupId).toArray()
  /** @param {string} entityType */
  const entityIds = (entityType) =>
    new Set(
      operations
        .filter((operation) => operation.entity_type === entityType)
        .map((operation) => operation.entity_id),
    )
  const participantIds = entityIds('participant')
  const expenseIds = entityIds('expense')
  const itemIds = entityIds('attachment_item')
  const optOutIds = new Set(
    operations
      .filter((operation) => operation.entity_type === 'attachment_opt_out')
      .map((operation) => `${operation.meta?.attachment_id}:${operation.entity_id}`),
  )
  const attachmentIds = new Set(
    operations
      .filter((operation) => operation.meta?.attachment_id)
      .map((operation) => operation.meta.attachment_id),
  )
  for (const operation of operations) {
    if (operation.entity_type === 'attachment_upload') attachmentIds.add(operation.entity_id)
  }
  const groupPending = operations.some((operation) => operation.entity_type === 'group')

  const anyOf = (table, key, ids) => (ids.size ? table.where(key).anyOf([...ids]).toArray() : [])
  const [group, participants, expenses, paidFor, attachments, items, portions, optOuts] =
    await Promise.all([
      groupPending ? db.groups.get(groupId) : null,
      anyOf(db.participants, 'id', participantIds),
      anyOf(db.expenses, 'id', expenseIds),
      anyOf(db.paidFor, 'expense_id', expenseIds),
      anyOf(db.attachments, 'id', attachmentIds),
      anyOf(db.attachmentItems, 'id', itemIds),
      anyOf(db.attachmentPortions, 'item_id', itemIds),
      anyOf(db.attachmentOptOuts, 'id', optOutIds),
    ])
  return { group, participants, expenses, paidFor, attachments, items, portions, optOuts }
}

/**
 * Replace one group's cached entities with a bootstrap snapshot.
 *
 * Pending local rows are captured first and re-applied afterwards so a
 * bootstrap (including the cursor-recovery path) does not drop unsynced edits.
 *
 * @param {any} snapshot
 * @param {{cursor?: number|null, scope?: string|null}} [options]
 */
export async function replaceGroupSnapshot(snapshot, options = {}) {
  const group = snapshot.group
  if (!group) return
  const groupId = group.id
  const now = nowIso()
  await db.transaction(
    'rw',
    [
      db.groups,
      db.participants,
      db.expenses,
      db.paidFor,
      db.attachments,
      db.attachmentItems,
      db.attachmentPortions,
      db.attachmentOptOuts,
      db.activities,
      db.categories,
      db.userGroups,
      db.outbox,
    ],
    async () => {
      const pending = await capturePendingSnapshotState(groupId)
      const existing = await db.groups.get(groupId)
      await db.groups.put({
        ...group,
        participants: undefined,
        user_group: undefined,
        is_starred: undefined,
        is_archived: undefined,
        isStarred: undefined,
        isArchived: undefined,
        pending: existing?.pending || false,
        list_only: false,
        cached_at: now,
      })
      if (pending.group) {
        await db.groups.put({
          ...pending.group,
          pending: true,
          list_only: false,
          cached_at: now,
        })
      }

      const participants = Array.isArray(snapshot.participants) ? snapshot.participants : []
      await db.participants.where('group_id').equals(groupId).delete()
      await db.participants.bulkPut(
        participants.map((participant, index) => ({
          ...participant,
          group_id: groupId,
          position: index,
          pending: false,
        })),
      )
      if (pending.participants.length) {
        await db.participants.bulkPut(pending.participants.map((row) => ({ ...row, pending: true })))
      }

      const expenses = Array.isArray(snapshot.expenses) ? snapshot.expenses : []
      const expenseIds = expenses.map((expense) => expense.id)
      await db.expenses.where('group_id').equals(groupId).delete()
      if (expenseIds.length) {
        await db.paidFor.where('expense_id').anyOf(expenseIds).delete()
      }
      const oldAttachments = await db.attachments.where('group_id').equals(groupId).toArray()
      const oldAttachmentIds = oldAttachments.map((row) => row.id)
      const oldItems = oldAttachmentIds.length
        ? await db.attachmentItems.where('attachment_id').anyOf(oldAttachmentIds).toArray()
        : []
      if (oldItems.length) {
        await db.attachmentPortions
          .where('item_id')
          .anyOf(oldItems.map((item) => item.id))
          .delete()
      }
      if (oldAttachmentIds.length) {
        await db.attachmentItems.where('attachment_id').anyOf(oldAttachmentIds).delete()
        await db.attachmentOptOuts.where('attachment_id').anyOf(oldAttachmentIds).delete()
      }
      await db.attachments.where('group_id').equals(groupId).delete()

      const paidForRows = []
      const attachmentRows = []
      for (const expense of expenses) {
        const { paid_for: paidFor, attachments, category: _category, ...base } = expense
        await db.expenses.put({
          ...base,
          category_id: Number(base.category_id || _category?.id || 0),
          pending: false,
        })
        for (const row of paidFor || []) {
          paidForRows.push({ ...row, expense_id: expense.id })
        }
        for (const attachment of attachments || []) {
          attachmentRows.push({ ...attachment, expense_id: expense.id, pending: false })
        }
      }

      const itemRows = []
      const portionRows = []
      const optOutRows = []
      const snapshots = Array.isArray(snapshot.attachments) ? snapshot.attachments : []
      for (const entry of snapshots) {
        const attachment = entry.attachment || {}
        if (!attachment.id) continue
        attachmentRows.push({ ...attachment, pending: false })
        for (const item of entry.items || []) itemRows.push(item)
        for (const portion of entry.portions || []) portionRows.push(portion)
        for (const optOut of entry.opt_outs || []) optOutRows.push(optOut)
      }
      if (paidForRows.length) await db.paidFor.bulkPut(paidForRows)
      if (attachmentRows.length) await db.attachments.bulkPut(attachmentRows)
      if (itemRows.length) await db.attachmentItems.bulkPut(itemRows)
      if (portionRows.length) await db.attachmentPortions.bulkPut(portionRows)
      if (optOutRows.length) await db.attachmentOptOuts.bulkPut(optOutRows)
      if (pending.expenses.length) {
        await db.expenses.bulkPut(pending.expenses.map((row) => ({ ...row, pending: true })))
      }
      if (pending.paidFor.length) await db.paidFor.bulkPut(pending.paidFor)
      if (pending.attachments.length) await db.attachments.bulkPut(pending.attachments)
      if (pending.items.length) {
        await db.attachmentItems.bulkPut(pending.items.map((row) => ({ ...row, pending: true })))
      }
      if (pending.portions.length) await db.attachmentPortions.bulkPut(pending.portions)
      if (pending.optOuts.length) await db.attachmentOptOuts.bulkPut(pending.optOuts)

      const activities = Array.isArray(snapshot.activities) ? snapshot.activities : []
      await db.activities.where('group_id').equals(groupId).delete()
      if (activities.length) await db.activities.bulkPut(activities)

      const categories = Array.isArray(snapshot.categories) ? snapshot.categories : []
      if (categories.length) await db.categories.bulkPut(categories)

      const membership = snapshot.user_group
      if (membership) {
        await db.userGroups.put({
          ...membership,
          id: `${membership.user_id}:${membership.group_id}`,
        })
      }
    },
  )
  if (options.scope && options.cursor != null) {
    await writeCursor(options.scope, Number(options.cursor))
  }
}

/**
 * Apply one full-snapshot change from `/sync/pull`.
 *
 * @param {{entity_type: string, entity_id: string, op_type: string, snapshot: any}} change
 */
export async function applySyncChange(change) {
  const snapshot = change.snapshot
  if (!snapshot) return
  if (change.entity_type === 'group') {
    const existing = await db.groups.get(change.entity_id)
    await db.groups.put({
      ...snapshot,
      participants: undefined,
      user_group: undefined,
      is_starred: undefined,
      is_archived: undefined,
      isStarred: undefined,
      isArchived: undefined,
      pending: existing?.pending || false,
      list_only: existing ? Boolean(existing.list_only) : true,
      cached_at: existing?.cached_at ?? null,
    })
    return
  }
  if (change.entity_type === 'participant') {
    const existing = await db.participants.get(change.entity_id)
    await db.participants.put({
      ...snapshot,
      position: existing?.position ?? 0,
      pending: existing?.pending || false,
    })
    return
  }
  if (change.entity_type === 'expense') {
    const { paid_for: paidFor, attachments, category: _category, ...base } = snapshot
    const existing = await db.expenses.get(change.entity_id)
    await db.expenses.put({
      ...base,
      pending: existing?.pending || false,
    })
    const oldAttachments = await db.attachments
      .where('expense_id')
      .equals(change.entity_id)
      .toArray()
    const incomingAttachments = Array.isArray(attachments) ? attachments : oldAttachments
    const incomingIds = new Set(incomingAttachments.map((/** @type {any} */ row) => row.id))
    // Expense snapshots carry attachment metadata but not their receipt items.
    // Keep the existing item/portion/opt-out rows for attachments that remain,
    // otherwise every unrelated expense update would erase the itemized split.
    const removedIds = oldAttachments
      .filter((row) => !incomingIds.has(row.id))
      .map((row) => row.id)
    const removedItems = removedIds.length
      ? await db.attachmentItems.where('attachment_id').anyOf(removedIds).toArray()
      : []
    if (removedItems.length) {
      await db.attachmentPortions
        .where('item_id')
        .anyOf(removedItems.map((item) => item.id))
        .delete()
    }
    if (removedIds.length) {
      await db.attachmentItems.where('attachment_id').anyOf(removedIds).delete()
      await db.attachmentOptOuts.where('attachment_id').anyOf(removedIds).delete()
      await db.attachments.where('id').anyOf(removedIds).delete()
    }
    await db.paidFor.where('expense_id').equals(change.entity_id).delete()
    if (base.deleted_at == null) {
      if (paidFor?.length) {
        await db.paidFor.bulkPut(
          paidFor.map((row) => ({ ...row, expense_id: change.entity_id })),
        )
      }
      if (incomingAttachments.length) {
        await db.attachments.bulkPut(
          incomingAttachments.map((row) => ({
            ...row,
            expense_id: change.entity_id,
            pending: false,
          })),
        )
      }
    } else if (oldAttachments.length) {
      // The whole expense is gone, so its attachments and receipt details are
      // gone too.
      const allIds = oldAttachments.map((row) => row.id)
      const allItems = await db.attachmentItems.where('attachment_id').anyOf(allIds).toArray()
      if (allItems.length) {
        await db.attachmentPortions
          .where('item_id')
          .anyOf(allItems.map((item) => item.id))
          .delete()
      }
      await db.attachmentItems.where('attachment_id').anyOf(allIds).delete()
      await db.attachmentOptOuts.where('attachment_id').anyOf(allIds).delete()
      await db.attachments.where('expense_id').equals(change.entity_id).delete()
    }
    return
  }
  if (change.entity_type === 'user_group') {
    const id = `${snapshot.user_id}:${snapshot.group_id}`
    if (change.op_type === 'delete' || snapshot.deleted_at) {
      await db.userGroups.delete(id)
    } else {
      await db.userGroups.put({ ...snapshot, id })
    }
  }
}

/**
 * Persist a canonical entity returned by a push result.
 *
 * @param {string} entityType
 * @param {string} entityId
 * @param {any} entity
 * @param {string} opType
 */
export async function applyPushEntity(entityType, entityId, entity, opType) {
  await applySyncChange({
    entity_type: entityType,
    entity_id: entityId,
    op_type: opType,
    snapshot: entity,
  })
  if (entityType === 'expense') {
    const existing = await db.expenses.get(entityId)
    if (existing) await db.expenses.put({ ...existing, pending: false })
  }
  if (entityType === 'participant') {
    const existing = await db.participants.get(entityId)
    if (existing) await db.participants.put({ ...existing, pending: false })
  }
  if (entityType === 'group') {
    const existing = await db.groups.get(entityId)
    if (existing) await db.groups.put({ ...existing, pending: false })
  }
}

/**
 * Remove a group that the server reports as not found.
 *
 * Pending operations for the group are dropped too: a permanent 404 cannot be
 * retried, and keeping them would leave an invisible failed queue forever.
 *
 * @param {string} groupId
 */
export async function deleteLocalGroup(groupId) {
  await db.transaction(
    'rw',
    [
      db.groups,
      db.participants,
      db.expenses,
      db.paidFor,
      db.attachments,
      db.attachmentItems,
      db.attachmentPortions,
      db.attachmentOptOuts,
      db.activities,
      db.userGroups,
      db.outbox,
      db.conflicts,
      db.blobs,
      db.metadata,
    ],
    async () => {
      const expenseIds = (await db.expenses.where('group_id').equals(groupId).toArray()).map(
        (row) => row.id,
      )
      const attachments = await db.attachments.where('group_id').equals(groupId).toArray()
      const attachmentIds = attachments.map((row) => row.id)
      const items = attachmentIds.length
        ? await db.attachmentItems.where('attachment_id').anyOf(attachmentIds).toArray()
        : []
      if (expenseIds.length) await db.paidFor.where('expense_id').anyOf(expenseIds).delete()
      if (items.length) {
        await db.attachmentPortions
          .where('item_id')
          .anyOf(items.map((item) => item.id))
          .delete()
      }
      if (attachmentIds.length) {
        await db.attachmentItems.where('attachment_id').anyOf(attachmentIds).delete()
        await db.attachmentOptOuts.where('attachment_id').anyOf(attachmentIds).delete()
      }
      await db.expenses.where('group_id').equals(groupId).delete()
      await db.participants.where('group_id').equals(groupId).delete()
      await db.activities.where('group_id').equals(groupId).delete()
      await db.attachments.where('group_id').equals(groupId).delete()
      await db.userGroups.where('group_id').equals(groupId).delete()
      await db.outbox.where('group_id').equals(groupId).delete()
      await db.conflicts.where('group_id').equals(groupId).delete()
      await db.blobs.where('group_id').equals(groupId).delete()
      await db.groups.delete(groupId)
      const recent = (await getMetadata('recentGroups', [])) || []
      const starred = new Set((await getMetadata('starredGroups', [])) || [])
      const archived = new Set((await getMetadata('archivedGroups', [])) || [])
      starred.delete(groupId)
      archived.delete(groupId)
      await db.metadata.put({
        key: 'recentGroups',
        value: recent.filter((entry) => entry.id !== groupId),
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
}

/**
 * @returns {Promise<void>}
 */
export async function clearAllData() {
  await db.transaction('rw', db.tables, async () => {
    for (const table of db.tables) await table.clear()
  })
}
