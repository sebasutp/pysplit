// @ts-nocheck
// Dexie tables are untyped at runtime; the repository contract tests cover shapes.
/**
 * Offline synchronization engine.
 *
 * Push then pull, single-flight across tabs, durable cursor per user/guest
 * scope, tombstone handling and an explicit conflict queue for financial edits.
 */

import { api } from './api'
import {
  applyPushEntity,
  applySyncChange,
  db,
  deleteLocalGroup,
  getMetadata,
  isOnline,
  newId,
  nowIso,
  readCursor,
  replaceGroupSnapshot,
  writeCursor,
} from './db'
import {
  discardFailed as discardFailedOperations,
  enqueue,
  failedCount,
  markApplied,
  markFailed,
  pendingCount,
  pendingGroupIdsInOrder,
  pendingOperations,
  removeOperation,
  retryFailed as retryFailedOperations,
} from './outbox'
import { getSyncStatus, setSyncStatus } from './sync-events'

/** @type {Promise<any>|null} */
let inFlight = null
/** @type {ReturnType<typeof setTimeout>|null} */
let debounceTimer = null
/** @type {ReturnType<typeof setInterval>|null} */
let intervalTimer = null
/** @type {BroadcastChannel|null} */
let channel = null
let started = false

/**
 * @param {string|null} userId
 * @returns {string}
 */
export function scopeFor(userId) {
  return userId ? `user:${userId}` : 'guest'
}

/** @returns {Promise<string>} */
async function currentScope() {
  const user = await getMetadata('session_user')
  return scopeFor(user?.id || null)
}

/** @param {number} pending */
async function refreshCounters(pending = null) {
  const [count, failed, conflicts] = await Promise.all([
    pending == null ? pendingCount() : pending,
    failedCount(),
    db.conflicts.count(),
  ])
  setSyncStatus({
    pending: count,
    failed,
    conflicts,
    online: isOnline(),
    phase: !isOnline() ? 'offline' : conflicts ? 'conflict' : getSyncStatus().phase,
  })
  return { count, failed, conflicts }
}

/** @param {any[]} operations */
function envelopes(operations) {
  return operations.map((row) => ({
    op_id: row.op_id,
    group_id: row.group_id,
    entity_type: row.entity_type,
    entity_id: row.entity_id,
    op_type: row.op_type,
    ...(row.base_version != null ? { base_version: row.base_version } : {}),
    payload: row.payload || {},
    client_time: row.client_time,
  }))
}

/**
 * Persist a group create result. The push endpoint returns a flat group
 * snapshot that includes participants; the historical `{group, participants}`
 * shape is still accepted for bootstrap-style callers.
 *
 * @param {any} snapshot
 * @returns {Promise<void>}
 */
async function storeGroupSnapshot(snapshot) {
  const group = snapshot.group || snapshot
  if (!group?.id) return
  await db.groups.put({
    ...group,
    participants: undefined,
    user_group: undefined,
    is_starred: undefined,
    is_archived: undefined,
    isStarred: undefined,
    isArchived: undefined,
    pending: false,
    list_only: false,
    cached_at: nowIso(),
  })
  const participants = snapshot.participants || group.participants || []
  const participantOperations = await db.outbox
    .where('group_id')
    .equals(group.id)
    .filter((row) => row.entity_type === 'participant')
    .toArray()
  const pendingParticipantIds = participantOperations.map((row) => row.entity_id)
  const pendingParticipants = pendingParticipantIds.length
    ? await db.participants.where('id').anyOf(pendingParticipantIds).toArray()
    : []
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
}

/**
 * @param {any} result
 * @param {any} operation
 * @returns {Promise<'applied'|'conflict'|'error'>}
 */
async function handleResult(result, operation) {
  if (result.status === 'applied') {
    if (result.entity) {
      if (operation.entity_type === 'group' && operation.op_type === 'create') {
        // The group-create response is a flat snapshot with participants.
        // Clearing them here prevents offline-created participants from
        // staying pending forever.
        await storeGroupSnapshot(result.entity)
      }
      await applyPushEntity(
        operation.entity_type,
        operation.entity_id,
        result.entity,
        operation.op_type,
      )
    }
    await markApplied(operation.op_id)
    return 'applied'
  }

  if (result.status === 'conflict') {
    await db.conflicts.add({
      op_id: operation.op_id,
      group_id: operation.group_id,
      entity_type: operation.entity_type,
      entity_id: operation.entity_id,
      op_type: operation.op_type,
      payload: operation.payload || {},
      base_version: operation.base_version ?? null,
      server_entity: result.server_entity || null,
      server_version: result.version ?? null,
      created_at: nowIso(),
    })
    await removeOperation(operation.op_id)
    await db.expenses.update(operation.entity_id, { pending: true }).catch(() => 0)
    await db.participants.update(operation.entity_id, { pending: true }).catch(() => 0)
    setSyncStatus({ phase: 'conflict' })
    return 'conflict'
  }

  const code = String(result.code || 'error')
  const retryable = ['network', 'server', 'rate_limited', 'conflict'].includes(code)
  await markFailed(
    operation.op_id,
    result.detail || result.code || 'Synchronization failed',
    retryable,
  )
  setSyncStatus({ phase: 'error', lastError: result.detail || String(result.code || 'error') })
  return 'error'
}

/**
 * Push one REST-transport operation (receipt item edits).
 *
 * @param {any} operation
 */
async function pushRestOperation(operation) {
  const meta = operation.meta || {}
  const groupPath = `/groups/${encodeURIComponent(operation.group_id)}`
  const receiptPath = `${groupPath}/receipts/${encodeURIComponent(meta.receipt_id || '')}`
  if (operation.entity_type === 'receipt_item') {
    if (operation.op_type === 'create') {
      // The server accepts a client id so a retried create is idempotent and
      // later portions/updates can address the same item.
      return api.post(`${receiptPath}/items`, {
        body: { ...operation.payload, id: operation.entity_id },
      })
    }
    const itemPath = `${receiptPath}/items/${encodeURIComponent(operation.entity_id)}`
    if (operation.op_type === 'delete') return api.delete(itemPath)
    return api.patch(itemPath, { body: operation.payload })
  }
  if (operation.entity_type === 'receipt_portion') {
    return api.put(
      `${receiptPath}/items/${encodeURIComponent(meta.item_id || operation.entity_id)}/portions`,
      { body: { portions: operation.payload?.portions || [] } },
    )
  }
  if (operation.entity_type === 'receipt_opt_out') {
    return api.put(
      `${receiptPath}/opt-outs/${encodeURIComponent(meta.participant_id || operation.entity_id)}`,
      { body: { opted_out: Boolean(operation.payload?.opted_out) } },
    )
  }
  throw new Error(`Unsupported REST operation ${operation.entity_type}`)
}

/**
 * Push pending operations in FIFO batches.
 *
 * @param {{groupId?: string|null, ignoreBackoff?: boolean}} [options]
 * @returns {Promise<{applied: number, conflicts: number, errors: number}>}
 */
export async function pushPending(options = {}) {
  const totals = { applied: 0, conflicts: 0, errors: 0 }
  if (!isOnline()) {
    await refreshCounters()
    return totals
  }

  const groupIds = options.groupId
    ? [options.groupId]
    : await pendingGroupIdsInOrder()

  /** @param {any[]} syncBatch @returns {Promise<void>} */
  async function flushSync(syncBatch) {
    if (!syncBatch.length) return
    let response
    try {
      response = await api.post('/sync/push', {
        body: { operations: envelopes(syncBatch) },
      })
    } catch (error) {
      const code =
        error && typeof error === 'object' && 'code' in error ? String(error.code) : 'network'
      for (const operation of syncBatch) {
        await markFailed(
          operation.op_id,
          error instanceof Error ? error.message : 'Push failed',
          ['network', 'server', 'rate_limited'].includes(code),
        )
      }
      throw error
    }

    const byOp = new Map(
      (response?.results || []).map((/** @type {any} */ result) => [result.op_id, result]),
    )
    // A failed head must not let later operations for the same group cascade.
    // Leave them pending for the next cycle instead of applying their results.
    let blocked = false
    for (const operation of syncBatch) {
      if (blocked) break
      const result = byOp.get(operation.op_id)
      if (!result) {
        await markFailed(operation.op_id, 'Missing push result', true)
        totals.errors += 1
        blocked = true
        continue
      }
      const status = await handleResult(result, operation)
      totals[status === 'applied' ? 'applied' : status === 'conflict' ? 'conflicts' : 'errors'] += 1
      if (status !== 'applied') blocked = true
    }
  }

  const receiptGroups = new Set()
  for (const groupId of groupIds) {
    for (;;) {
      const batch = await pendingOperations({
        groupId,
        limit: 50,
        ignoreBackoff: Boolean(options.ignoreBackoff),
      })
      if (!batch.length) break
      const progressBefore = totals.applied + totals.conflicts
      try {
        /** @type {any[]} */
        let syncBatch = []
        for (const operation of batch) {
          if (operation.transport === 'rest') {
            await flushSync(syncBatch)
            syncBatch = []
            try {
              await pushRestOperation(operation)
              await markApplied(operation.op_id)
              receiptGroups.add(groupId)
              totals.applied += 1
            } catch (error) {
              const code =
                error && typeof error === 'object' && 'code' in error
                  ? String(error.code)
                  : 'network'
              await markFailed(
                operation.op_id,
                error instanceof Error ? error.message : 'Push failed',
                ['network', 'server', 'rate_limited'].includes(code),
              )
              if (['network', 'server', 'rate_limited'].includes(code)) throw error
              totals.errors += 1
              // Stop this group at its first non-retryable REST failure.
              break
            }
          } else {
            syncBatch.push(operation)
          }
        }
        await flushSync(syncBatch)
      } catch (error) {
        const code =
          error && typeof error === 'object' && 'code' in error ? String(error.code) : 'network'
        if (['network', 'server', 'rate_limited'].includes(code)) {
          setSyncStatus({ phase: 'error', lastError: 'Unable to reach the server' })
          await refreshCounters()
          scheduleSync({ delay: 1500 })
          return totals
        }
      }
      if (batch.length < 50) break
      // A forced sync ignores backoff; without this guard a full batch of
      // retryable failures would be selected again forever.
      if (totals.applied + totals.conflicts === progressBefore) break
    }
  }
  // Only receipt mutations need a snapshot refresh; ordinary expense pushes
  // already return their canonical entity.
  for (const groupId of receiptGroups) {
    await bootstrapGroup(groupId, { updateCursor: false }).catch(() => {})
  }

  await refreshCounters()
  return totals
}


/**
 * Pull and apply full snapshots until the feed is exhausted.
 *
 * @returns {Promise<{applied: number}>}
 */
export async function pullChanges() {
  if (!isOnline()) return { applied: 0 }
  const scope = await currentScope()
  const groups = await db.groups.toArray()
  const groupIds = groups.map((group) => group.id)
  if (!groupIds.length) return { applied: 0 }

  const startCursor = await readCursor(scope)
  let finalCursor = startCursor
  let applied = 0
  const touched = new Set()
  const removed = new Set()

  /** @type {string[][]} */
  const chunks = []
  for (let index = 0; index < groupIds.length; index += 500) {
    chunks.push(groupIds.slice(index, index + 500))
  }

  for (const groupChunk of chunks) {
    // Each chunk starts from the same committed cursor. Changes for an earlier
    // chunk are applied before the next chunk advances past them, so a global
    // cursor never skips another chunk's rows.
    let cursor = startCursor
    for (;;) {
      let response
      try {
        response = await api.post('/sync/pull', {
          body: { cursor, group_ids: groupChunk, limit: 500 },
        })
      } catch (error) {
        const code =
          error && typeof error === 'object' && 'code' in error ? String(error.code) : 'network'
        if (code === 'conflict') {
          // The cursor predates retention (or is ahead of the server). Bootstrap
          // every group and resume from the highest snapshot cursor. Groups the
          // server no longer has are removed locally instead of aborting the pull.
          let recoveredCursor = 0
          for (const groupId of groupIds) {
            try {
              const snapshot = await bootstrapGroup(groupId, { updateCursor: false })
              recoveredCursor = Math.max(recoveredCursor, Number(snapshot?.cursor || 0))
            } catch (bootstrapError) {
              const bootstrapCode =
                bootstrapError && typeof bootstrapError === 'object' && 'code' in bootstrapError
                  ? String(bootstrapError.code)
                  : null
              if (bootstrapCode === 'not_found' || bootstrapCode === 'forbidden') {
                await deleteLocalGroup(groupId)
                continue
              }
              throw bootstrapError
            }
          }
          await writeCursor(scope, recoveredCursor)
          return { applied }
        }
        throw error
      }

      const changes = response?.changes || []
      await db.transaction('rw', db.tables, async () => {
        for (const change of changes) {
          await applySyncChange(change)
          if (change.group_id) touched.add(change.group_id)
          if (
            change.entity_type === 'user_group' &&
            (change.op_type === 'delete' || change.snapshot?.deleted_at) &&
            change.snapshot?.group_id
          ) {
            removed.add(change.snapshot.group_id)
          }
          applied += 1
        }
      })
      if (response?.cursor != null) {
        cursor = Number(response.cursor)
        finalCursor = Math.max(finalCursor, cursor)
      }
      if (!response?.has_more) break
    }
  }

  await writeCursor(scope, finalCursor)
  for (const groupId of removed) {
    await deleteLocalGroup(groupId)
  }
  for (const groupId of touched) {
    if (removed.has(groupId)) continue
    await refreshActivities(groupId).catch(() => {})
  }
  return { applied }
}

/**
 * @param {string} groupId
 * @param {{updateCursor?: boolean}} [options]
 * @returns {Promise<any>}
 */
export async function bootstrapGroup(groupId, options = {}) {
  const scope = await currentScope()
  const snapshot = await api.get(
    `/sync/bootstrap?group_id=${encodeURIComponent(groupId)}`,
  )
  await replaceGroupSnapshot(snapshot)
  if (options.updateCursor !== false && !(await readCursor(scope))) {
    const cursor = Number(snapshot?.cursor || 0)
    if (cursor) await writeCursor(scope, cursor)
  }
  return snapshot
}

/**
 * @param {string} groupId
 * @returns {Promise<void>}
 */
export async function refreshActivities(groupId) {
  if (!isOnline()) return
  const payload = await api.get(
    `/groups/${encodeURIComponent(groupId)}/activities?limit=100`,
  )
  const items = payload?.items || []
  await db.activities.where('group_id').equals(groupId).delete()
  if (items.length) await db.activities.bulkPut(items)
}

/**
 * Prefetch recently visited groups in the background.
 *
 * @param {string[]} groupIds
 */
export async function prefetchGroups(groupIds) {
  if (!isOnline() || !groupIds.length) return
  let changed = false
  for (const groupId of groupIds) {
    const cached = await db.groups.get(groupId)
    // Only prefetch groups that the list cache actually accepted. A pending
    // leave is skipped by the cache writer and must not be resurrected here.
    if (!cached) continue
    if (cached.cached_at && !cached.list_only) continue
    try {
      await bootstrapGroup(groupId, { updateCursor: false })
      changed = true
    } catch {
      // Prefetch is best-effort; a failed group must not block startup.
    }
  }
  if (changed && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('pysplit:refresh'))
  }
}

/**
 * Single sync cycle: push pending work, then pull snapshots.
 *
 * @param {{reason?: string, force?: boolean, ignoreBackoff?: boolean}} [options]
 * @returns {Promise<{applied: number, conflicts: number, errors: number}>}
 */
export async function runSync(options = {}) {
  if (!isOnline()) {
    await refreshCounters()
    setSyncStatus({ phase: 'offline' })
    return { applied: 0, conflicts: 0, errors: 0 }
  }
  await refreshCounters()
  setSyncStatus({ phase: 'syncing' })
  try {
    const pushed = await pushPending({ ignoreBackoff: Boolean(options.force) })
    const pulled = await pullChanges()
    const { count, conflicts } = await refreshCounters()
    setSyncStatus({
      phase: conflicts ? 'conflict' : 'idle',
      pending: count,
      conflicts,
      lastError: null,
      lastSyncedAt: nowIso(),
      online: true,
    })
    broadcast()
    return { ...pushed, applied: pushed.applied + pulled.applied, reason: options.reason }
  } catch (error) {
    await refreshCounters()
    setSyncStatus({
      phase: 'error',
      lastError: error instanceof Error ? error.message : 'Synchronization failed',
    })
    return { applied: 0, conflicts: 0, errors: 1 }
  }
}

/**
 * Online trigger with cross-tab single-flight.
 *
 * @param {{reason?: string, force?: boolean, ignoreBackoff?: boolean}} [options]
 * @returns {Promise<any>}
 */
export function syncNow(options = {}) {
  if (inFlight) return inFlight
  const task = async () => {
    if (typeof navigator !== 'undefined' && navigator.locks?.request) {
      // A forced sync waits for another tab instead of bypassing the lock; an
      // automatic sync may skip when another tab is already working.
      return navigator.locks.request(
        'pysplit-sync',
        { ifAvailable: !options.force },
        async (lock) => {
          if (!lock) {
            scheduleSync({ delay: 2000 })
            return { skipped: true }
          }
          return runSync(options)
        },
      )
    }
    return runSync(options)
  }
  inFlight = task().finally(() => {
    inFlight = null
  })
  return inFlight
}

/**
 * Debounced trigger used after a local mutation.
 *
 * @param {{delay?: number}} [options]
 */
export function scheduleSync(options = {}) {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    void syncNow({ reason: 'mutation' })
  }, options.delay ?? 250)
}

function broadcast() {
  try {
    channel?.postMessage({ type: 'synced', at: nowIso() })
  } catch {
    // BroadcastChannel is optional.
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('pysplit:refresh'))
  }
}

function handleOnline() {
  setSyncStatus({ online: true, phase: 'syncing' })
  void syncNow({ reason: 'online' })
}

function handleOffline() {
  setSyncStatus({ online: false, phase: 'offline' })
}

function handleVisibility() {
  if (document.visibilityState === 'visible' && isOnline()) {
    void syncNow({ reason: 'visibility' })
  }
}

/**
 * Start the background triggers. Safe to call more than once.
 */
export function startSync() {
  if (started || typeof window === 'undefined') return
  started = true
  setSyncStatus({ online: isOnline() })

  if (typeof BroadcastChannel !== 'undefined') {
    channel = new BroadcastChannel('pysplit-sync')
    channel.addEventListener('message', (event) => {
      if (event.data?.type === 'synced') {
        void refreshCounters()
        window.dispatchEvent(new CustomEvent('pysplit:refresh'))
      }
    })
  }

  window.addEventListener('online', handleOnline)
  window.addEventListener('offline', handleOffline)
  document.addEventListener('visibilitychange', handleVisibility)

  intervalTimer = setInterval(() => {
    if (isOnline()) void syncNow({ reason: 'interval' })
  }, 60_000)

  void refreshCounters()
  void syncNow({ reason: 'start' })
}

/**
 * Stop timers, listeners and wait for an in-flight cycle before callers clear
 * local data for an account change.
 *
 * @returns {Promise<void>}
 */
export async function stopSync() {
  if (typeof window !== 'undefined') {
    window.removeEventListener('online', handleOnline)
    window.removeEventListener('offline', handleOffline)
    document.removeEventListener('visibilitychange', handleVisibility)
  }
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
  if (intervalTimer) clearInterval(intervalTimer)
  intervalTimer = null
  channel?.close()
  channel = null
  started = false
  if (inFlight) {
    try {
      await inFlight
    } catch {
      // A failed cycle must not block logout or an account switch.
    }
  }
  // An in-flight cycle may have scheduled a retry while it was finishing.
  if (debounceTimer) {
    clearTimeout(debounceTimer)
    debounceTimer = null
  }
}

/**
 * @returns {Promise<any[]>}
 */
export async function listConflicts() {
  return db.conflicts.orderBy('created_at').reverse().toArray()
}

/**
 * Resolve a conflict using the UI's explicit choice.
 *
 * @param {number} conflictId
 * @param {'mine'|'server'|'duplicate'} strategy
 */
export async function resolveConflict(conflictId, strategy) {
  const conflict = await db.conflicts.get(conflictId)
  if (!conflict) return
  const server = conflict.server_entity

  if (strategy === 'server') {
    if (server) {
      await applySyncChange({
        entity_type: conflict.entity_type,
        entity_id: conflict.entity_id,
        op_type: 'update',
        snapshot: server,
      })
      const table =
        conflict.entity_type === 'participant'
          ? db.participants
          : conflict.entity_type === 'group'
            ? db.groups
            : db.expenses
      await table.update(conflict.entity_id, { pending: false }).catch(() => 0)
    }
    await db.conflicts.delete(conflictId)
    await refreshCounters()
    return
  }

  if (strategy === 'mine') {
    const baseVersion = Number(server?.version ?? conflict.server_version ?? 0)
    const timestamp = nowIso()
    const table =
      conflict.entity_type === 'participant'
        ? db.participants
        : conflict.entity_type === 'group'
          ? db.groups
          : db.expenses
    await db.transaction(
      'rw',
      [db.expenses, db.participants, db.groups, db.paidFor, db.outbox],
      async () => {
        if (conflict.op_type === 'delete') {
          await table.update(conflict.entity_id, {
            deleted_at: timestamp,
            updated_at: timestamp,
            pending: true,
          })
        } else if (conflict.entity_type === 'expense') {
          const { paid_for: paidFor, participant_id: _participantId, ...fields } =
            conflict.payload || {}
          await db.expenses.update(conflict.entity_id, {
            ...fields,
            updated_at: timestamp,
            pending: true,
          })
          if (Array.isArray(paidFor)) {
            await db.paidFor.where('expense_id').equals(conflict.entity_id).delete()
            if (paidFor.length) {
              await db.paidFor.bulkPut(
                paidFor.map((row) => ({ ...row, expense_id: conflict.entity_id })),
              )
            }
          }
        } else {
          const { paid_for: _paidFor, ...fields } = conflict.payload || {}
          await table.update(conflict.entity_id, {
            ...fields,
            updated_at: timestamp,
            pending: true,
          })
        }
        await enqueue({
          op_id: newId('op'),
          group_id: conflict.group_id,
          entity_type: conflict.entity_type,
          entity_id: conflict.entity_id,
          op_type: conflict.op_type || 'update',
          base_version: baseVersion,
          payload: conflict.payload,
        })
      },
    )
    await db.conflicts.delete(conflictId)
    await refreshCounters()
    scheduleSync({ delay: 0 })
    return
  }

  // Duplicate as new: create a fresh entity from the local payload.
  if (conflict.entity_type === 'expense') {
    const local = (await db.expenses.get(conflict.entity_id)) || {}
    const id = newId('exp')
    const timestamp = nowIso()
    // The pull after a conflict has already replaced the local row with the
    // server snapshot, so the user's edit lives in the stored operation payload.
    const payload = {
      expense_date: conflict.payload?.expense_date ?? local.expense_date,
      title: conflict.payload?.title ?? local.title,
      category_id: Number(conflict.payload?.category_id ?? local.category_id ?? 0),
      amount: Number(conflict.payload?.amount ?? local.amount ?? 0),
      original_amount: conflict.payload?.original_amount ?? local.original_amount ?? null,
      original_currency: conflict.payload?.original_currency ?? local.original_currency ?? null,
      conversion_rate: conflict.payload?.conversion_rate ?? local.conversion_rate ?? null,
      paid_by_id: conflict.payload?.paid_by_id || local.paid_by_id,
      is_reimbursement: Boolean(conflict.payload?.is_reimbursement ?? local.is_reimbursement),
      split_mode: conflict.payload?.split_mode || local.split_mode || 'EVENLY',
      notes: conflict.payload?.notes ?? local.notes ?? null,
      recurrence_rule: conflict.payload?.recurrence_rule || local.recurrence_rule || 'NONE',
      paid_for:
        conflict.payload?.paid_for ??
        (await db.paidFor.where('expense_id').equals(conflict.entity_id).toArray()).map(
          (row) => ({ participant_id: row.participant_id, shares: row.shares }),
        ),
    }
    await db.transaction('rw', [db.expenses, db.paidFor, db.outbox], async () => {
      await db.expenses.put({
        id,
        group_id: conflict.group_id,
        ...payload,
        created_at: timestamp,
        updated_at: timestamp,
        version: 0,
        deleted_at: null,
        pending: true,
      })
      const rows = payload.paid_for.map((row) => ({ ...row, expense_id: id }))
      if (rows.length) await db.paidFor.bulkPut(rows)
      await enqueue({
        op_id: newId('op'),
        group_id: conflict.group_id,
        entity_type: 'expense',
        entity_id: id,
        op_type: 'create',
        payload,
      })
    })
    await db.expenses.update(conflict.entity_id, { pending: false }).catch(() => 0)
    await db.conflicts.delete(conflictId)
    await refreshCounters()
    scheduleSync({ delay: 0 })
  }
}

/** Move permanently failed operations back to pending. */
export async function retryFailed() {
  await retryFailedOperations()
  await refreshCounters()
  scheduleSync({ delay: 0 })
}

/** Discard permanently failed operations after user acknowledgement. */
export async function discardFailed() {
  const rows = await db.outbox.where('status').equals('failed').toArray()
  const groups = new Set()
  const removedGroups = new Set()
  for (const row of rows) {
    if (row.op_type !== 'create') {
      if (row.group_id) groups.add(row.group_id)
      continue
    }
    if (row.entity_type === 'group') {
      removedGroups.add(row.group_id)
      await deleteLocalGroup(row.group_id)
      continue
    }
    if (row.group_id) groups.add(row.group_id)
    if (row.entity_type === 'expense') {
      await db.expenses.delete(row.entity_id)
      await db.paidFor.where('expense_id').equals(row.entity_id).delete()
      await db.documents.where('expense_id').equals(row.entity_id).delete()
    } else if (row.entity_type === 'participant') {
      await db.participants.delete(row.entity_id)
    } else if (row.entity_type === 'receipt_item') {
      await db.receiptItems.delete(row.entity_id)
      await db.receiptPortions.where('item_id').equals(row.entity_id).delete()
    } else if (row.entity_type === 'receipt_opt_out') {
      const id = `${row.meta?.receipt_id}:${row.entity_id}`
      await db.receiptOptOuts.delete(id)
    }
  }
  await discardFailedOperations()
  for (const groupId of groups) {
    if (removedGroups.has(groupId)) continue
    if (isOnline()) {
      await bootstrapGroup(groupId, { updateCursor: false }).catch(() => {})
    } else {
      // Offline: clear the pending marker so the UI stops showing a ghost. The
      // next bootstrap will replace the local row with server state.
      const expenseIds = rowEntityIds(rows, 'expense', groupId)
      const participantIds = rowEntityIds(rows, 'participant', groupId)
      if (expenseIds.length) {
        await db.expenses.where('id').anyOf(expenseIds).modify({ pending: false })
      }
      if (participantIds.length) {
        await db.participants.where('id').anyOf(participantIds).modify({ pending: false })
      }
    }
  }
  await refreshCounters()
}

/**
 * @param {any[]} rows
 * @param {string} entityType
 * @param {string} groupId
 * @returns {any}
 */
function rowEntityIds(rows, entityType, groupId) {
  return rows
    .filter((row) => row.group_id === groupId && row.entity_type === entityType)
    .map((row) => row.entity_id)
}
