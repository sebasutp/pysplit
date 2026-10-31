import { beforeEach, describe, expect, it } from 'vitest'

import { db } from './db'
import { resolveConflict } from './sync'

async function seedConflict() {
  await db.expenses.put({
    id: 'e1',
    group_id: 'g1',
    expense_date: '2026-03-01',
    title: 'Server title',
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
  return Number(await db.conflicts.add({
    op_id: 'op1',
    group_id: 'g1',
    entity_type: 'expense',
    entity_id: 'e1',
    op_type: 'update',
    payload: { title: 'Local title', amount: 1000, paid_for: [] },
    base_version: 1,
    server_entity: {
      id: 'e1',
      group_id: 'g1',
      expense_date: '2026-03-01',
      title: 'Server title',
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
      paid_for: [{ participant_id: 'a', shares: 1 }],
      attachments: [],
    },
    server_version: 2,
    created_at: '2026-03-01T00:00:00Z',
  }))
}

beforeEach(async () => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
  await db.transaction('rw', db.tables, async () => {
    for (const table of db.tables) await table.clear()
  })
})

describe('conflict resolution strategies', () => {
  it('uses the server entity and clears the pending flag', async () => {
    const id = await seedConflict()
    await resolveConflict(id, 'server')

    expect(await db.conflicts.count()).toBe(0)
    expect((await db.expenses.get('e1')).title).toBe('Server title')
    expect((await db.expenses.get('e1')).pending).toBe(false)
    expect(await db.outbox.count()).toBe(0)
  })

  it('keeps mine by re-queuing against the server version', async () => {
    const id = await seedConflict()
    await resolveConflict(id, 'mine')

    const outbox = await db.outbox.toArray()
    expect(outbox).toHaveLength(1)
    expect(outbox[0]).toMatchObject({
      entity_type: 'expense',
      op_type: 'update',
      base_version: 2,
      payload: { title: 'Local title' },
    })
    expect(await db.conflicts.count()).toBe(0)
  })

  it('preserves a delete when keeping mine', async () => {
    const id = await seedConflict()
    await db.conflicts.update(id, { op_type: 'delete', payload: {} })

    await resolveConflict(id, 'mine')

    const outbox = await db.outbox.toArray()
    expect(outbox).toHaveLength(1)
    expect(outbox[0]).toMatchObject({
      entity_type: 'expense',
      op_type: 'delete',
      base_version: 2,
    })
    expect((await db.expenses.get('e1')).deleted_at).toBeTruthy()
    expect(await db.conflicts.count()).toBe(0)
  })

  it('duplicates the local payload as a brand-new expense', async () => {
    const id = await seedConflict()
    await resolveConflict(id, 'duplicate')

    const outbox = await db.outbox.toArray()
    expect(outbox).toHaveLength(1)
    expect(outbox[0]).toMatchObject({
      entity_type: 'expense',
      op_type: 'create',
      payload: { title: 'Local title' },
    })
    const created = await db.expenses.get(outbox[0].entity_id)
    expect(created.title).toBe('Local title')
    expect(created.id).not.toBe('e1')
    expect(await db.conflicts.count()).toBe(0)
  })
})
