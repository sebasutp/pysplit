// @ts-nocheck
/**
 * @vitest-environment jsdom
 */
import 'fake-indexeddb/auto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../services/api', () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
  },
}))

import { api } from '../services/api'
import { applySyncChange, db, replaceGroupSnapshot } from '../services/db'
import { enqueue } from '../services/outbox'
import { localRepository, ready } from '../services/repository/local'
import { getSyncStatus } from '../services/sync-events'
import {
  discardFailed,
  pullChanges,
  resolveConflict,
  stopSync,
  syncNow,
} from '../services/sync'

async function resetDb() {
  await ready()
  window.localStorage.clear()
  await db.transaction('rw', db.tables, async () => {
    for (const table of db.tables) await table.clear()
  })
  await db.categories.bulkPut([
    { id: 0, grouping: 'Uncategorized', name: 'General' },
    { id: 1, grouping: 'Food and Drink', name: 'Groceries' },
  ])
  await db.groups.put({
    id: 'g1',
    name: 'Trip',
    information: null,
    currency: '$',
    currency_code: 'USD',
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    version: 1,
    deleted_at: null,
    list_only: false,
  })
  await db.participants.bulkPut([
    {
      id: 'a',
      name: 'Alice',
      group_id: 'g1',
      updated_at: '2026-01-01T00:00:00.000Z',
      version: 1,
      deleted_at: null,
      position: 0,
    },
    {
      id: 'b',
      name: 'Bob',
      group_id: 'g1',
      updated_at: '2026-01-01T00:00:00.000Z',
      version: 1,
      deleted_at: null,
      position: 1,
    },
  ])
}

beforeEach(async () => {
  vi.clearAllMocks()
  await resetDb()
})

afterEach(async () => {
  await stopSync()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('Offline Synchronization Bug Reproductions (offline_sync_review.md)', () => {
  // Bug 1a
  it('Bug 1a: resolveConflict("duplicate") sets version: 1 on duplicated expense and does not produce base_version: 0 update', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    await db.expenses.put({
      id: 'e1',
      group_id: 'g1',
      expense_date: '2026-03-01',
      title: 'Conflicted Dinner',
      category_id: 0,
      amount: 1000,
      paid_by_id: 'a',
      is_reimbursement: false,
      split_mode: 'EVENLY',
      notes: null,
      recurrence_rule: 'NONE',
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
      version: 2,
      deleted_at: null,
      pending: true,
    })
    await db.paidFor.bulkPut([
      { expense_id: 'e1', participant_id: 'a', shares: 1 },
      { expense_id: 'e1', participant_id: 'b', shares: 1 },
    ])
    const conflictId = Number(
      await db.conflicts.add({
        op_id: 'op1',
        group_id: 'g1',
        entity_type: 'expense',
        entity_id: 'e1',
        op_type: 'update',
        payload: { title: 'Local title', amount: 1000 },
        base_version: 1,
        server_entity: {
          id: 'e1',
          group_id: 'g1',
          expense_date: '2026-03-01',
          title: 'Server title',
          category_id: 0,
          amount: 2000,
          paid_by_id: 'a',
          is_reimbursement: false,
          split_mode: 'EVENLY',
          notes: null,
          recurrence_rule: 'NONE',
          created_at: '2026-03-01T00:00:00Z',
          updated_at: '2026-03-01T00:00:00Z',
          version: 2,
          deleted_at: null,
          paid_for: [{ participant_id: 'a', shares: 1 }],
          attachments: [],
        },
        server_version: 2,
        created_at: '2026-03-01T00:00:00Z',
      }),
    )

    await resolveConflict(conflictId, 'duplicate')

    const outboxAfterDup = await db.outbox.toArray()
    const createOp = outboxAfterDup.find((op) => op.op_type === 'create')
    expect(createOp).toBeDefined()
    const newExpenseId = createOp.entity_id
    const duplicatedExpense = await db.expenses.get(newExpenseId)

    // Bug 1a assertion: resolveConflict('duplicate') should set version: 1 (not 0) on duplicated expense
    expect(duplicatedExpense.version).toBe(1)

    // And subsequent offline edit should not generate an update operation with base_version: 0
    await localRepository.expenses.update('g1', newExpenseId, { title: 'Edited Duplicate' })
    const allOps = await db.outbox.where('entity_id').equals(newExpenseId).toArray()
    const updateOp = allOps.find((op) => op.op_type === 'update')
    if (updateOp) {
      expect(updateOp.base_version).not.toBe(0)
    }
  })

  // Bug 1b
  it('Bug 1b: sequential offline mutations to the same expense coalesce in db.outbox', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    // Seed existing synced expense at version 1
    await db.expenses.put({
      id: 'e_synced',
      group_id: 'g1',
      expense_date: '2026-03-01',
      title: 'Synced Dinner',
      category_id: 0,
      amount: 1000,
      paid_by_id: 'a',
      is_reimbursement: false,
      split_mode: 'EVENLY',
      notes: null,
      recurrence_rule: 'NONE',
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
      version: 1,
      deleted_at: null,
      pending: false,
    })
    await db.paidFor.bulkPut([
      { expense_id: 'e_synced', participant_id: 'a', shares: 1 },
      { expense_id: 'e_synced', participant_id: 'b', shares: 1 },
    ])

    // Update the same expense twice offline before sync
    await localRepository.expenses.update('g1', 'e_synced', { title: 'First Edit', amount: 1500 })
    await localRepository.expenses.update('g1', 'e_synced', { title: 'Second Edit', amount: 2000 })

    const outboxUpdates = await db.outbox.where('entity_id').equals('e_synced').toArray()
    // Should coalesce into a single update keeping base_version: 1 and merged payload
    expect(outboxUpdates).toHaveLength(1)
    expect(outboxUpdates[0].base_version).toBe(1)
    expect(outboxUpdates[0].payload.title).toBe('Second Edit')
    expect(outboxUpdates[0].payload.amount).toBe(2000)
  })

  // Bug 2
  it('Bug 2: runSync/syncNow preserves phase: "error" and lastError when push encounters non-retryable failure', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    await enqueue({
      op_id: 'op_bad',
      group_id: 'g1',
      entity_type: 'expense',
      entity_id: 'e_bad',
      op_type: 'update',
      base_version: 1,
      payload: { amount: -500 },
    })

    api.post.mockImplementation((path) => {
      if (path === '/sync/push') {
        return Promise.resolve({
          results: [
            {
              op_id: 'op_bad',
              status: 'error',
              code: 'validation_error',
              detail: 'Amount must be positive',
            },
          ],
          cursor: 0,
        })
      }
      if (path === '/sync/pull') {
        return Promise.resolve({ changes: [], cursor: 0, has_more: false })
      }
      return Promise.resolve({})
    })

    await syncNow()

    const status = getSyncStatus()
    expect(status.phase).toBe('error')
    expect(status.lastError).toContain('Amount must be positive')
  })

  // Bug 5
  it('Bug 5: resolveConflict("duplicate") preserves non-empty paid_for from server_entity when db.paidFor is cleared', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    const conflictId = Number(
      await db.conflicts.add({
        op_id: 'op_del_conflict',
        group_id: 'g1',
        entity_type: 'expense',
        entity_id: 'e_del',
        op_type: 'update',
        payload: { title: 'My updated title' }, // partial payload without paid_for
        base_version: 1,
        server_entity: {
          id: 'e_del',
          group_id: 'g1',
          expense_date: '2026-03-01',
          title: 'Deleted Expense',
          category_id: 0,
          amount: 3000,
          paid_by_id: 'a',
          is_reimbursement: false,
          split_mode: 'BY_AMOUNT',
          notes: null,
          recurrence_rule: 'NONE',
          created_at: '2026-03-01T00:00:00Z',
          updated_at: '2026-03-01T00:00:00Z',
          version: 2,
          deleted_at: '2026-03-01T12:00:00Z',
          paid_for: [
            { participant_id: 'a', shares: 1, amount: 1500 },
            { participant_id: 'b', shares: 1, amount: 1500 },
          ],
          attachments: [],
        },
        server_version: 2,
        created_at: '2026-03-01T00:00:00Z',
      }),
    )

    // Clear db.paidFor to emulate pullChanges() having deleted rows for the deleted expense
    await db.paidFor.where('expense_id').equals('e_del').delete()

    await resolveConflict(conflictId, 'duplicate')

    const outbox = await db.outbox.toArray()
    const createOp = outbox.find((op) => op.op_type === 'create')
    expect(createOp).toBeDefined()
    expect(createOp.payload.paid_for).toBeDefined()
    expect(createOp.payload.paid_for.length).toBeGreaterThan(0)
    expect(createOp.payload.paid_for).toEqual([
      { participant_id: 'a', shares: 1, amount: 1500 },
      { participant_id: 'b', shares: 1, amount: 1500 },
    ])
  })

  // Bug 6
  it('Bug 6: creating + attaching a file + deleting an expense offline cleans up pending attachment upload and local paidFor', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    const exp = await localRepository.expenses.create('g1', {
      title: 'Dinner to Delete',
      amount: 1000,
      paid_by_id: 'a',
      paid_for: [
        { participant_id: 'a', shares: 1 },
        { participant_id: 'b', shares: 1 },
      ],
    })

    const file = new File(['dummy binary data'], 'receipt.png', { type: 'image/png' })
    await localRepository.attachments.upload('g1', file, { expense_id: exp.id })

    // Delete the expense offline
    await localRepository.expenses.remove('g1', exp.id)

    // Assert pending blob attachment upload is cancelled/unlinked in db.outbox
    const allOps = await db.outbox.toArray()
    const blobOps = allOps.filter((op) => op.transport === 'blob')
    const expBlobOps = blobOps.filter((op) => op.payload?.expense_id === exp.id)
    expect(expBlobOps).toHaveLength(0)

    // Assert db.paidFor rows are cleaned up
    const paidForRows = await db.paidFor.where('expense_id').equals(exp.id).toArray()
    expect(paidForRows).toHaveLength(0)
  })

  // Bug 7
  it('Bug 7: localRepository.attachments.link succeeds offline by linking attachment and updating outbox', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    const file = new File(['dummy binary data'], 'receipt.png', { type: 'image/png' })
    const att = await localRepository.attachments.upload('g1', file, {})
    const exp = await localRepository.expenses.create('g1', {
      title: 'Dinner for Receipt',
      amount: 2000,
      paid_by_id: 'a',
      paid_for: [{ participant_id: 'a', shares: 1 }],
    })

    // Calling link offline currently throws RepositoryError with code 'offline_unsupported'
    await localRepository.attachments.link('g1', att.id, exp.id)

    const updatedAtt = await db.attachments.get(att.id)
    expect(updatedAtt.expense_id).toBe(exp.id)

    const uploadOp = await db.outbox
      .where('entity_id')
      .equals(att.id)
      .and((op) => op.transport === 'blob')
      .first()
    expect(uploadOp.payload?.expense_id).toBe(exp.id)
  })

  // Bug 8
  it('Bug 8: replaceGroupSnapshot preserves pending: true for entities with unresolved conflicts in db.conflicts', async () => {
    await db.expenses.put({
      id: 'e_conflicted',
      group_id: 'g1',
      expense_date: '2026-03-01',
      title: 'Local Title',
      category_id: 0,
      amount: 1000,
      paid_by_id: 'a',
      is_reimbursement: false,
      split_mode: 'EVENLY',
      notes: null,
      recurrence_rule: 'NONE',
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
      version: 2,
      deleted_at: null,
      pending: true,
    })

    // Conflict exists in db.conflicts, no corresponding row in db.outbox
    await db.conflicts.add({
      op_id: 'op_c1',
      group_id: 'g1',
      entity_type: 'expense',
      entity_id: 'e_conflicted',
      op_type: 'update',
      payload: { title: 'Local Title' },
      base_version: 1,
      server_entity: {
        id: 'e_conflicted',
        group_id: 'g1',
        title: 'Server Title',
        version: 2,
      },
      server_version: 2,
      created_at: '2026-03-01T00:00:00Z',
    })

    // Server bootstrap snapshot applied via replaceGroupSnapshot
    await replaceGroupSnapshot({
      group: { id: 'g1', name: 'Trip', version: 2 },
      expenses: [
        {
          id: 'e_conflicted',
          group_id: 'g1',
          expense_date: '2026-03-01',
          title: 'Server Title',
          category_id: 0,
          amount: 1000,
          paid_by_id: 'a',
          is_reimbursement: false,
          split_mode: 'EVENLY',
          notes: null,
          recurrence_rule: 'NONE',
          created_at: '2026-03-01T00:00:00Z',
          updated_at: '2026-03-01T00:00:00Z',
          version: 2,
          deleted_at: null,
        },
      ],
      participants: [],
      categories: [],
      activities: [],
      attachments: [],
    })

    const exp = await db.expenses.get('e_conflicted')
    expect(exp.pending).toBe(true)
  })

  // Bug 9
  it('Bug 9: discardFailed() while offline restores pre-mutation clean state instead of leaving deleted_at or modified state with pending: false', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    await db.expenses.put({
      id: 'e_clean',
      group_id: 'g1',
      expense_date: '2026-03-01',
      title: 'Clean Dinner',
      category_id: 0,
      amount: 1000,
      paid_by_id: 'a',
      is_reimbursement: false,
      split_mode: 'EVENLY',
      notes: null,
      recurrence_rule: 'NONE',
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
      version: 1,
      deleted_at: null,
      pending: false,
    })
    await db.paidFor.bulkPut([
      { expense_id: 'e_clean', participant_id: 'a', shares: 1 },
      { expense_id: 'e_clean', participant_id: 'b', shares: 1 },
    ])

    await db.expenses.put({
      id: 'e_tombstone',
      group_id: 'g1',
      expense_date: '2026-03-01',
      title: 'Tombstoned Dinner',
      category_id: 0,
      amount: 500,
      paid_by_id: 'a',
      is_reimbursement: false,
      split_mode: 'EVENLY',
      notes: null,
      recurrence_rule: 'NONE',
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
      version: 1,
      deleted_at: null,
      pending: false,
    })
    await db.paidFor.bulkPut([
      { expense_id: 'e_tombstone', participant_id: 'a', shares: 1 },
      { expense_id: 'e_tombstone', participant_id: 'b', shares: 1 },
    ])

    // Offline update on e_clean that fails
    await localRepository.expenses.update('g1', 'e_clean', {
      title: 'Rejected Edit',
      amount: 9999,
    })
    await db.outbox.where('entity_id').equals('e_clean').modify({ status: 'failed' })

    // Offline delete on e_tombstone that fails
    await localRepository.expenses.remove('g1', 'e_tombstone')
    await db.outbox.where('entity_id').equals('e_tombstone').modify({ status: 'failed' })

    // User calls discardFailed while offline
    await discardFailed()

    const restoredClean = await db.expenses.get('e_clean')
    // Discarding failed update must restore pre-mutation clean title, amount, and deleted_at: null
    expect(restoredClean.deleted_at).toBeNull()
    expect(restoredClean.title).toBe('Clean Dinner')
    expect(restoredClean.amount).toBe(1000)

    const restoredTombstone = await db.expenses.get('e_tombstone')
    // Discarding failed delete must restore deleted_at to null so the expense is not permanently tombstoned
    expect(restoredTombstone.deleted_at).toBeNull()
  })

  // Bug 10
  it('Bug 10: pullChanges() excludes list_only: true groups from /api/sync/pull group_ids', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    await db.groups.clear()
    await db.groups.put({
      id: 'g1_bootstrapped',
      name: 'Bootstrapped Group',
      version: 1,
      list_only: false,
    })
    await db.groups.put({
      id: 'g2_unbootstrapped',
      name: 'List Only Group',
      version: 1,
      list_only: true,
    })

    api.post.mockImplementation((path) => {
      if (path === '/sync/pull') {
        return Promise.resolve({ changes: [], cursor: 10, has_more: false })
      }
      return Promise.resolve({})
    })

    await pullChanges()

    const pullCalls = api.post.mock.calls.filter((call) => call[0] === '/sync/pull')
    expect(pullCalls.length).toBeGreaterThan(0)
    const queriedGroupIds = pullCalls[0][1].body.group_ids
    expect(queriedGroupIds).not.toContain('g2_unbootstrapped')
    expect(queriedGroupIds).toEqual(['g1_bootstrapped'])
  })

  // Bug 11
  it('Bug 11: push result with status: "error", code: "conflict" is treated as non-retryable (status: "failed" in outbox)', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    await enqueue({
      op_id: 'op_domain_conflict',
      group_id: 'g1',
      entity_type: 'expense',
      entity_id: 'e1',
      op_type: 'update',
      base_version: 1,
      payload: { recurrence_rule: 'MONTHLY' },
    })

    api.post.mockImplementation((path) => {
      if (path === '/sync/push') {
        return Promise.resolve({
          results: [
            {
              op_id: 'op_domain_conflict',
              status: 'error',
              code: 'conflict',
              detail: 'recurring expense rule cannot change after materialization',
            },
          ],
          cursor: 0,
        })
      }
      if (path === '/sync/pull') {
        return Promise.resolve({ changes: [], cursor: 0, has_more: false })
      }
      return Promise.resolve({})
    })

    await syncNow()

    const op = await db.outbox.where('op_id').equals('op_domain_conflict').first()
    expect(op.status).toBe('failed')
  })

  // Bug 12a
  it('Bug 12a: groups.update coalesces participant mutations in db.outbox and removes offline-created participants that are deleted', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    // First update: rename Alice to 'Alice Renamed 1', keep Bob, add Charlie
    await localRepository.groups.update('g1', {
      name: 'Trip 1',
      participants: [
        { id: 'a', name: 'Alice Renamed 1' },
        { id: 'b', name: 'Bob' },
        { name: 'Charlie' },
      ],
    })
    // Second update: rename Alice to 'Alice Renamed 2', keep Bob, remove Charlie
    await localRepository.groups.update('g1', {
      name: 'Trip 2',
      participants: [
        { id: 'a', name: 'Alice Renamed 2' },
        { id: 'b', name: 'Bob' },
      ],
    })

    const outbox = await db.outbox.toArray()
    const aliceOps = outbox.filter(
      (op) => op.entity_type === 'participant' && op.entity_id === 'a',
    )
    // Must coalesce into a single update op for Alice
    expect(aliceOps).toHaveLength(1)
    expect(aliceOps[0].base_version).toBe(1)
    expect(aliceOps[0].payload.name).toBe('Alice Renamed 2')

    // Must cancel/clean up offline created then removed participant Charlie
    const charlieOps = outbox.filter(
      (op) =>
        op.entity_type === 'participant' &&
        op.entity_id !== 'a' &&
        op.entity_id !== 'b',
    )
    expect(charlieOps).toHaveLength(0)
  })

  // Bug 12b
  it('Bug 12b: deleting an unsynced offline-created expense cancels create op and leaves 0 expense ops in outbox', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    const exp = await localRepository.expenses.create('g1', {
      title: 'Offline Expense to Cancel',
      amount: 1500,
      paid_by_id: 'a',
      paid_for: [{ participant_id: 'a', shares: 1 }],
    })

    const createdOps = await db.outbox.where('entity_id').equals(exp.id).toArray()
    expect(createdOps).toHaveLength(1)
    expect(createdOps[0].op_type).toBe('create')

    // Delete the expense offline before it is synced
    await localRepository.expenses.remove('g1', exp.id)

    const outboxAfter = await db.outbox.where('entity_id').equals(exp.id).toArray()
    // Should cancel the pending create and not enqueue a delete, leaving 0 ops
    expect(outboxAfter).toHaveLength(0)

    // Should remove from db.expenses rather than leaving a tombstone
    const expRow = await db.expenses.get(exp.id)
    expect(expRow).toBeUndefined()
  })

  // Bug 13
  it('Bug 13: resolveConflict("mine") recreates expense as live (deleted_at: null, version: 1) with create op when server deleted it', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    const conflictId = Number(
      await db.conflicts.add({
        op_id: 'op_mine_conflict',
        group_id: 'g1',
        entity_type: 'expense',
        entity_id: 'e_server_deleted',
        op_type: 'update',
        base_version: 1,
        payload: {
          title: 'My Kept Dinner',
          amount: 3500,
          paid_by_id: 'a',
          split_mode: 'EVENLY',
        },
        server_entity: {
          id: 'e_server_deleted',
          group_id: 'g1',
          expense_date: '2026-03-01',
          title: 'Original Dinner',
          category_id: 0,
          amount: 3000,
          paid_by_id: 'a',
          is_reimbursement: false,
          split_mode: 'EVENLY',
          notes: null,
          recurrence_rule: 'NONE',
          created_at: '2026-03-01T00:00:00Z',
          updated_at: '2026-03-01T00:00:00Z',
          version: 2,
          deleted_at: '2026-03-01T12:00:00Z',
          paid_for: [
            { participant_id: 'a', shares: 1 },
            { participant_id: 'b', shares: 1 },
          ],
          attachments: [],
        },
        server_version: 2,
        created_at: '2026-03-01T00:00:00Z',
      }),
    )

    // Emulate pullChanges having applied server deletion
    await db.expenses.put({
      id: 'e_server_deleted',
      group_id: 'g1',
      expense_date: '2026-03-01',
      title: 'Original Dinner',
      category_id: 0,
      amount: 3000,
      paid_by_id: 'a',
      is_reimbursement: false,
      split_mode: 'EVENLY',
      notes: null,
      recurrence_rule: 'NONE',
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
      version: 2,
      deleted_at: '2026-03-01T12:00:00Z',
      pending: true,
    })
    await db.paidFor.where('expense_id').equals('e_server_deleted').delete()

    // User chooses "Keep mine"
    await resolveConflict(conflictId, 'mine')

    const outbox = await db.outbox.toArray()
    expect(outbox).toHaveLength(1)
    // When server deleted the entity, keeping mine MUST queue a 'create' op, not an 'update' op
    expect(outbox[0].op_type).toBe('create')
    expect(outbox[0].payload.title).toBe('My Kept Dinner')
    expect(outbox[0].payload.paid_for).toBeDefined()
    expect(outbox[0].payload.paid_for.length).toBeGreaterThan(0)

    const localExpense = await db.expenses.get(outbox[0].entity_id)
    expect(localExpense.deleted_at).toBeNull()
    expect(localExpense.version).toBe(1)

    const paidForRows = await db.paidFor
      .where('expense_id')
      .equals(outbox[0].entity_id)
      .toArray()
    expect(paidForRows.length).toBeGreaterThan(0)
  })

  // Bug 14a
  it('Bug 14a: applySyncChange does not delete pending local attachments when server snapshot has empty attachments', async () => {
    await db.expenses.put({
      id: 'e1',
      group_id: 'g1',
      expense_date: '2026-03-01',
      title: 'Dinner',
      category_id: 0,
      amount: 1000,
      paid_by_id: 'a',
      is_reimbursement: false,
      split_mode: 'EVENLY',
      notes: null,
      recurrence_rule: 'NONE',
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
      version: 1,
      deleted_at: null,
      pending: false,
    })

    await db.attachments.put({
      id: 'att_local',
      group_id: 'g1',
      expense_id: 'e1',
      filename: 'receipt.png',
      content_type: 'image/png',
      byte_size: 100,
      pending: true,
      pending_upload: true,
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T00:00:00Z',
      version: 1,
      deleted_at: null,
    })

    await applySyncChange({
      seq: 5,
      group_id: 'g1',
      entity_type: 'expense',
      entity_id: 'e1',
      op_type: 'update',
      snapshot: {
        id: 'e1',
        group_id: 'g1',
        expense_date: '2026-03-01',
        title: 'Dinner Updated Remotely',
        category_id: 0,
        amount: 1200,
        paid_by_id: 'a',
        is_reimbursement: false,
        split_mode: 'EVENLY',
        notes: null,
        recurrence_rule: 'NONE',
        created_at: '2026-03-01T00:00:00Z',
        updated_at: '2026-03-01T01:00:00Z',
        version: 2,
        deleted_at: null,
        attachments: [],
        paid_for: [{ participant_id: 'a', shares: 1 }],
      },
    })

    const att = await db.attachments.get('att_local')
    expect(att).toBeDefined()
  })

  // Bug 14b
  it('Bug 14b: pullChanges does not clobber pending outbox edits when intermediate SyncChange arrives', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    await db.expenses.put({
      id: 'e1',
      group_id: 'g1',
      expense_date: '2026-03-01',
      title: 'Unsynced Local Edit',
      category_id: 0,
      amount: 4500,
      paid_by_id: 'a',
      is_reimbursement: false,
      split_mode: 'EVENLY',
      notes: null,
      recurrence_rule: 'NONE',
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-01T02:00:00Z',
      version: 2,
      deleted_at: null,
      pending: true,
    })
    await enqueue({
      op_id: 'op_pending_edit',
      group_id: 'g1',
      entity_type: 'expense',
      entity_id: 'e1',
      op_type: 'update',
      base_version: 1,
      payload: { title: 'Unsynced Local Edit', amount: 4500 },
    })

    api.post.mockImplementation((path) => {
      if (path === '/sync/pull') {
        return Promise.resolve({
          changes: [
            {
              seq: 3,
              group_id: 'g1',
              entity_type: 'expense',
              entity_id: 'e1',
              op_type: 'update',
              snapshot: {
                id: 'e1',
                group_id: 'g1',
                expense_date: '2026-03-01',
                title: 'Older Server Title',
                category_id: 0,
                amount: 1000,
                paid_by_id: 'a',
                is_reimbursement: false,
                split_mode: 'EVENLY',
                notes: null,
                recurrence_rule: 'NONE',
                created_at: '2026-03-01T00:00:00Z',
                updated_at: '2026-03-01T01:00:00Z',
                version: 2,
                deleted_at: null,
                attachments: [],
                paid_for: [{ participant_id: 'a', shares: 1 }],
              },
            },
          ],
          cursor: 3,
          has_more: false,
        })
      }
      return Promise.resolve({})
    })

    await pullChanges()

    const exp = await db.expenses.get('e1')
    expect(exp.title).toBe('Unsynced Local Edit')
    expect(exp.amount).toBe(4500)
    expect(exp.pending).toBe(true)
  })
})
