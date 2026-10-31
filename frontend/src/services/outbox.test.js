import { beforeEach, describe, expect, it } from 'vitest'

import { db, applySyncChange, replaceGroupSnapshot } from './db'
import {
  discardFailed,
  failedCount,
  outboxRow,
  pendingCount,
  pendingOperations,
  retryFailed,
} from './outbox'

/** @param {any} operation */
async function seedOutbox(operation) {
  return db.outbox.add(outboxRow(operation))
}

beforeEach(async () => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
  await db.transaction('rw', db.tables, async () => {
    for (const table of db.tables) await table.clear()
  })
})

describe('outbox ordering and failures', () => {
  it('stops at a backed-off head instead of skipping ahead within a group', async () => {
    await db.outbox.add({
      ...outboxRow({
        op_id: 'op1',
        group_id: 'g1',
        entity_type: 'expense',
        entity_id: 'e1',
        op_type: 'update',
      }),
      next_attempt_at: new Date(Date.now() + 60_000).toISOString(),
    })
    await seedOutbox({
      op_id: 'op2',
      group_id: 'g1',
      entity_type: 'expense',
      entity_id: 'e2',
      op_type: 'update',
    })
    await seedOutbox({
      op_id: 'op3',
      group_id: 'g2',
      entity_type: 'expense',
      entity_id: 'e3',
      op_type: 'update',
    })

    expect(await pendingOperations({ groupId: 'g1' })).toEqual([])
    // Other groups are not held back by g1's backed-off head.
    expect((await pendingOperations()).map((row) => row.op_id)).toEqual(['op3'])

    const due = new Date(Date.now() + 120_000).getTime()
    expect((await pendingOperations({ groupId: 'g1', now: due })).map((row) => row.op_id)).toEqual([
      'op1',
      'op2',
    ])
  })

  it('counts failed rows separately and can retry or discard them', async () => {
    await db.outbox.add({
      ...outboxRow({
        op_id: 'op-failed',
        group_id: 'g1',
        entity_type: 'expense',
        entity_id: 'e1',
        op_type: 'update',
      }),
      status: 'failed',
      last_error: 'validation',
    })
    await seedOutbox({
      op_id: 'op-pending',
      group_id: 'g2',
      entity_type: 'expense',
      entity_id: 'e2',
      op_type: 'update',
    })

    expect(await pendingCount()).toBe(1)
    expect(await failedCount()).toBe(1)

    await retryFailed()
    expect(await failedCount()).toBe(0)
    expect(await pendingCount()).toBe(2)

    await db.outbox.where('op_id').equals('op-failed').modify({ status: 'failed' })
    await discardFailed()
    expect(await failedCount()).toBe(0)
    expect(await db.outbox.where('op_id').equals('op-failed').count()).toBe(0)
  })

  it('preserves pending local rows when a bootstrap snapshot is applied', async () => {
    await db.groups.put({
      id: 'g1',
      name: 'Local name',
      currency: '$',
      version: 3,
      updated_at: '2026-02-01T00:00:00.000Z',
    })
    await db.participants.put({
      id: 'p-local',
      group_id: 'g1',
      name: 'Local participant',
      position: 0,
      version: 2,
      updated_at: '2026-02-01T00:00:00.000Z',
      pending: true,
    })
    await db.expenses.put({
      id: 'e-local',
      group_id: 'g1',
      title: 'Pending expense',
      amount: 1000,
      expense_date: '2026-02-01',
      version: 1,
      updated_at: '2026-02-01T00:00:00.000Z',
      pending: true,
    })
    await db.paidFor.put({ expense_id: 'e-local', participant_id: 'p-local', shares: 1 })
    await seedOutbox({
      op_id: 'op-p',
      group_id: 'g1',
      entity_type: 'participant',
      entity_id: 'p-local',
      op_type: 'create',
    })
    await seedOutbox({
      op_id: 'op-e',
      group_id: 'g1',
      entity_type: 'expense',
      entity_id: 'e-local',
      op_type: 'create',
    })

    await replaceGroupSnapshot({
      group: {
        id: 'g1',
        name: 'Server name',
        currency: '$',
        version: 4,
        updated_at: '2026-02-02T00:00:00.000Z',
      },
      participants: [],
      expenses: [],
      activities: [],
      attachments: [],
      categories: [],
    })

    expect((await db.groups.get('g1')).name).toBe('Server name')
    expect((await db.participants.get('p-local')).name).toBe('Local participant')
    expect(await db.expenses.get('e-local')).toMatchObject({
      title: 'Pending expense',
      pending: true,
    })
    expect(await db.paidFor.where('expense_id').equals('e-local').count()).toBe(1)
  })

  it('removes orphaned portions when replacing attachment snapshots', async () => {
    await db.groups.put({ id: 'g1', name: 'Trip', version: 1 })
    await db.attachments.put({ id: 'r1', group_id: 'g1', version: 1 })
    await db.attachmentItems.put({ id: 'old-item', attachment_id: 'r1', version: 1, position: 0 })
    await db.attachmentPortions.put({ id: 'old-portion', item_id: 'old-item', version: 1 })

    await replaceGroupSnapshot({
      group: { id: 'g1', name: 'Trip', version: 2 },
      participants: [],
      expenses: [],
      activities: [],
      attachments: [{ attachment: { id: 'r1', group_id: 'g1', version: 2 }, items: [], portions: [] }],
      categories: [],
    })

    expect(await db.attachmentPortions.where('item_id').equals('old-item').count()).toBe(0)
  })

  it('keeps receipt items when an expense snapshot update arrives', async () => {
    await db.attachments.put({
      id: 'r1',
      group_id: 'g1',
      expense_id: 'e1',
      receipt_status: 'EXTRACTED',
      version: 1,
    })
    await db.attachmentItems.put({
      id: 'item-1',
      attachment_id: 'r1',
      name: 'Pizza',
      amount: 1000,
      quantity_milli: 1000,
      position: 0,
      version: 1,
    })
    await db.attachmentPortions.put({
      id: 'portion-1',
      item_id: 'item-1',
      target: 'PARTICIPANT',
      participant_id: 'p1',
      quantity_milli: 1000,
      version: 1,
    })

    // Expense snapshots include attachment metadata but not the itemized split.
    await applySyncChange({
      entity_type: 'expense',
      entity_id: 'e1',
      op_type: 'update',
      snapshot: {
        id: 'e1',
        group_id: 'g1',
        title: 'Dinner',
        amount: 1000,
        version: 2,
        deleted_at: null,
        paid_for: [],
        attachments: [
          {
            id: 'r1',
            group_id: 'g1',
            expense_id: 'e1',
            receipt_status: 'EXTRACTED',
            version: 2,
          },
        ],
      },
    })

    expect(await db.attachmentItems.get('item-1')).toMatchObject({ name: 'Pizza' })
    expect(await db.attachmentPortions.get('portion-1')).toMatchObject({ participant_id: 'p1' })
    expect(await db.attachments.get('r1')).toMatchObject({ version: 2 })
  })

  it('removes receipt details when an expense snapshot drops an attachment', async () => {
    await db.attachments.put({
      id: 'r1',
      group_id: 'g1',
      expense_id: 'e1',
      receipt_status: 'EXTRACTED',
      version: 1,
    })
    await db.attachmentItems.put({ id: 'item-1', attachment_id: 'r1', version: 1, position: 0 })

    await applySyncChange({
      entity_type: 'expense',
      entity_id: 'e1',
      op_type: 'update',
      snapshot: {
        id: 'e1',
        group_id: 'g1',
        title: 'Dinner',
        amount: 1000,
        version: 2,
        deleted_at: null,
        paid_for: [],
        attachments: [],
      },
    })

    expect(await db.attachments.get('r1')).toBeUndefined()
    expect(await db.attachmentItems.get('item-1')).toBeUndefined()
  })
})
