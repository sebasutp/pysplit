// @ts-nocheck
// Dexie tables are untyped at runtime; the repository contract tests cover shapes.
/**
 * Durable outbox for offline mutations.
 *
 * Every write is applied to Dexie and appended here in the same transaction.
 * Operations are pushed FIFO per group in batches of at most 50.
 */

import { db, nowIso } from './db'

export const MAX_BATCH = 50

/** @typedef {'pending'|'failed'} OutboxStatus */

/**
 * @param {number} attempts
 * @returns {number} milliseconds until the next attempt
 */
export function backoffMs(attempts) {
  return Math.min(60_000, 1000 * 2 ** Math.min(attempts, 6))
}

/**
 * @param {{
 *   op_id: string,
 *   group_id: string,
 *   entity_type: string,
 *   entity_id: string,
 *   op_type: 'create'|'update'|'delete',
 *   base_version?: number|null,
 *   payload?: any,
 * }} operation
 */
export function outboxRow(operation) {
  return {
    op_id: operation.op_id,
    group_id: operation.group_id,
    entity_type: operation.entity_type,
    entity_id: operation.entity_id,
    op_type: operation.op_type,
    base_version: operation.base_version ?? null,
    payload: operation.payload ?? {},
    client_time: new Date().toISOString(),
    status: /** @type {OutboxStatus} */ ('pending'),
    attempts: 0,
    next_attempt_at: nowIso(),
    last_error: null,
    transport: operation.transport || 'sync',
    meta: operation.meta || {},
    created_at: nowIso(),
    updated_at: nowIso(),
  }
}

/**
 * Append an operation. Call inside the same Dexie transaction as the local
 * mutation when possible.
 *
 * @param {any} operation
 */
export async function enqueue(operation) {
  return db.outbox.add(outboxRow(operation))
}

/**
 * @param {{groupId?: string|null, limit?: number, now?: number, ignoreBackoff?: boolean}} [options]
 * @returns {Promise<any[]>}
 */
export async function pendingOperations(options = {}) {
  const now = options.now ?? Date.now()
  const limit = options.limit ?? MAX_BATCH
  const rows = await db.outbox.orderBy('seq').toArray()
  /** @type {any[]} */
  const result = []
  // FIFO per group: a backed-off or permanently failed head holds back every
  // later operation for the same group instead of being skipped.
  const blocked = new Set()
  for (const row of rows) {
    if (options.groupId && row.group_id !== options.groupId) continue
    if (blocked.has(row.group_id)) continue
    if (row.status === 'failed') {
      blocked.add(row.group_id)
      continue
    }
    if (row.status !== 'pending') continue
    if (
      !options.ignoreBackoff &&
      new Date(row.next_attempt_at).getTime() > now
    ) {
      blocked.add(row.group_id)
      continue
    }
    result.push(row)
    if (result.length >= limit) break
  }
  return result
}

/**
 * @returns {Promise<string[]>}
 */
export async function pendingGroupIdsInOrder() {
  const rows = await db.outbox.orderBy('seq').toArray()
  /** @type {string[]} */
  const order = []
  const seen = new Set()
  for (const row of rows) {
    if (row.status !== 'pending') continue
    if (seen.has(row.group_id)) continue
    seen.add(row.group_id)
    order.push(row.group_id)
  }
  return order
}

/** @returns {Promise<number>} */
export async function pendingCount() {
  return db.outbox.where('status').equals('pending').count()
}

/** @returns {Promise<number>} */
export async function failedCount() {
  return db.outbox.where('status').equals('failed').count()
}

/**
 * Move permanently failed rows back to pending so the next sync retries them.
 * The local entity keeps its `pending` flag, so no data is lost.
 */
export async function retryFailed() {
  const rows = await db.outbox.where('status').equals('failed').toArray()
  for (const row of rows) {
    await db.outbox.put({
      ...row,
      status: 'pending',
      attempts: 0,
      next_attempt_at: nowIso(),
      last_error: null,
      updated_at: nowIso(),
    })
  }
}

/** Remove permanently failed rows after the user has acknowledged them. */
export async function discardFailed() {
  const rows = await db.outbox.where('status').equals('failed').toArray()
  for (const row of rows) await db.outbox.delete(row.seq)
}

/**
 * @param {string} opId
 */
export async function markApplied(opId) {
  await db.outbox.where('op_id').equals(opId).delete()
}

/**
 * @param {string} opId
 * @param {string} detail
 * @param {boolean} retryable
 */
export async function markFailed(opId, detail, retryable) {
  const row = await db.outbox.where('op_id').equals(opId).first()
  if (!row) return
  const attempts = Number(row.attempts || 0) + 1
  await db.outbox.put({
    ...row,
    attempts,
    status: retryable ? 'pending' : 'failed',
    last_error: detail,
    next_attempt_at: retryable
      ? new Date(Date.now() + backoffMs(attempts)).toISOString()
      : row.next_attempt_at,
    updated_at: nowIso(),
  })
}

/**
 * @param {string} opId
 */
export async function removeOperation(opId) {
  await db.outbox.where('op_id').equals(opId).delete()
}
