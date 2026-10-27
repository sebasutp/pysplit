import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { db } from '../db'
import { outboxRow } from '../outbox'
import { onlineRepository } from './online'
import { REPOSITORY_METHODS } from './contract'
import { cacheUser, cachedUser, localRepository, ready } from './local'
import { stopSync } from '../sync'

/** @param {string} path */
function resolveMethod(path) {
  const parts = path.split('.')
  let current = /** @type {any} */ (localRepository)
  for (const part of parts) current = current?.[part]
  return current
}

async function reset() {
  await ready()
  window.localStorage.clear()
  await db.transaction('rw', db.tables, async () => {
    for (const table of db.tables) await table.clear()
  })
  await db.categories.bulkPut([
    { id: 0, grouping: 'Uncategorized', name: 'General' },
    { id: 9, grouping: 'Food and Drink', name: 'Groceries' },
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
  await db.expenses.put({
    id: 'e1',
    group_id: 'g1',
    expense_date: '2026-01-02',
    title: 'Dinner',
    category_id: 9,
    amount: 9000,
    original_amount: null,
    original_currency: null,
    conversion_rate: null,
    paid_by_id: 'a',
    is_reimbursement: false,
    split_mode: 'EVENLY',
    notes: null,
    recurrence_rule: 'NONE',
    created_at: '2026-01-02T10:00:00.000Z',
    updated_at: '2026-01-02T10:00:00.000Z',
    version: 1,
    deleted_at: null,
  })
  await db.paidFor.bulkPut([
    { expense_id: 'e1', participant_id: 'a', shares: 1 },
    { expense_id: 'e1', participant_id: 'b', shares: 1 },
  ])
  await db.activities.put({
    id: 'act1',
    group_id: 'g1',
    time: '2026-01-02T10:00:00.000Z',
    activity_type: 'EXPENSE_CREATED',
    participant_id: 'a',
    expense_id: 'e1',
    data: null,
  })
  await db.receipts.put({
    id: 'r1',
    group_id: 'g1',
    image_url: '/uploads/receipt.jpg',
    image_width: 100,
    image_height: 200,
    status: 'EXTRACTED',
    merchant: null,
    receipt_date: null,
    currency_code: 'USD',
    total: 1000,
    expense_id: null,
    created_at: '2026-01-02T10:00:00.000Z',
    updated_at: '2026-01-02T10:00:00.000Z',
    version: 1,
    deleted_at: null,
  })
  await db.receiptItems.put({
    id: 'i1',
    receipt_id: 'r1',
    name: 'Pizza',
    quantity_milli: 1000,
    unit_price: 1000,
    amount: 1000,
    is_shared: true,
    is_adjustment: false,
    position: 0,
    created_at: '2026-01-02T10:00:00.000Z',
    updated_at: '2026-01-02T10:00:00.000Z',
    version: 1,
    deleted_at: null,
  })
}

beforeEach(async () => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
  await reset()
})

afterEach(async () => {
  await stopSync()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('local repository', () => {
  it('implements every documented method', () => {
    for (const path of REPOSITORY_METHODS) {
      expect(typeof resolveMethod(path), path).toBe('function')
    }
  })

  it('serves groups, expenses, balances and statistics from Dexie', async () => {
    const group = await localRepository.groups.get('g1')
    expect(group.name).toBe('Trip')
    expect(group.participants.map((/** @type {any} */ row) => row.name)).toEqual(['Alice', 'Bob'])

    const listed = await localRepository.expenses.list('g1', { limit: 10 })
    expect(listed).toMatchObject({ total: 1, limit: 10, offset: 0 })
    expect(listed.items[0]).toMatchObject({ title: 'Dinner', amount: 9000 })
    expect(listed.items[0].paid_for).toHaveLength(2)

    const balances = await localRepository.balances.list('g1')
    expect(balances.balances).toEqual([
      { participant_id: 'a', total: 4500, paid: 4500, paid_for: 0 },
      { participant_id: 'b', total: -4500, paid: 0, paid_for: 4500 },
    ])
    expect(balances.reimbursements).toEqual([{ from: 'b', to: 'a', amount: 4500 }])

    const stats = await localRepository.stats.overview('g1')
    expect(stats.total_group_spending).toBe(9000)
    expect(stats.spending_by_category[0]).toMatchObject({ category_id: 9, total: 9000 })

    const activities = await localRepository.activities.list('g1', { limit: 5 })
    expect(activities.items[0].expense).toMatchObject({ title: 'Dinner', amount: 9000 })

    const receipt = await localRepository.receipts.get('g1', { receipt_id: 'r1' })
    expect(receipt.items).toHaveLength(1)
    expect(receipt.split.items_total).toBe(1000)
    expect(receipt.split.participants.map((/** @type {any} */ row) => row.total)).toEqual([500, 500])
  })

  it('applies offline writes and queues them in the outbox', async () => {
    const created = await localRepository.expenses.create('g1', {
      expense_date: '2026-02-01',
      title: 'Taxi',
      category_id: 0,
      amount: 3000,
      paid_by_id: 'a',
      split_mode: 'EVENLY',
      paid_for: [
        { participant_id: 'a', shares: 1 },
        { participant_id: 'b', shares: 1 },
      ],
    })
    expect(created.pending).toBe(true)
    const outbox = await db.outbox.toArray()
    expect(outbox).toHaveLength(1)
    expect(outbox[0]).toMatchObject({
      entity_type: 'expense',
      op_type: 'create',
      status: 'pending',
    })
    const listed = await localRepository.expenses.list('g1', { limit: 10 })
    expect(listed.total).toBe(2)
  })

  it('normalizes BY_AMOUNT shares to integer minor units locally and in the outbox', async () => {
    const created = await localRepository.expenses.create('g1', {
      expense_date: '2026-02-02',
      title: 'Tickets',
      category_id: 0,
      amount: 3000,
      paid_by_id: 'a',
      split_mode: 'BY_AMOUNT',
      paid_for: [
        { participant_id: 'a', amount: 1000 },
        { participant_id: 'b', amount: 2000 },
      ],
    })
    expect(created.paid_for).toEqual([
      { participant_id: 'a', shares: 1000 },
      { participant_id: 'b', shares: 2000 },
    ])
    const outbox = await db.outbox.toArray()
    expect(outbox[0].payload.paid_for).toEqual([
      { participant_id: 'a', shares: 1000 },
      { participant_id: 'b', shares: 2000 },
    ])
  })

  it('normalizes BY_PERCENTAGE percentages to basis points', async () => {
    const created = await localRepository.expenses.create('g1', {
      expense_date: '2026-02-03',
      title: 'Hotel',
      category_id: 0,
      amount: 3000,
      paid_by_id: 'a',
      split_mode: 'BY_PERCENTAGE',
      paid_for: [
        { participant_id: 'a', shares: 25 },
        { participant_id: 'b', shares: 75 },
      ],
    })
    expect(created.paid_for).toEqual([
      { participant_id: 'a', shares: 2500 },
      { participant_id: 'b', shares: 7500 },
    ])
    const outbox = await db.outbox.toArray()
    expect(outbox[0].payload.paid_for).toEqual([
      { participant_id: 'a', shares: 2500 },
      { participant_id: 'b', shares: 7500 },
    ])
  })

  it('normalizes an update payload using the new split mode', async () => {
    const updated = await localRepository.expenses.update('g1', 'e1', {
      amount: 5000,
      split_mode: 'BY_AMOUNT',
      paid_for: [
        { participant_id: 'a', amount: 2000 },
        { participant_id: 'b', amount: 3000 },
      ],
    })
    expect(updated.paid_for).toEqual([
      { participant_id: 'a', shares: 2000 },
      { participant_id: 'b', shares: 3000 },
    ])
    const outbox = await db.outbox.toArray()
    expect(outbox[0].payload.paid_for).toEqual([
      { participant_id: 'a', shares: 2000 },
      { participant_id: 'b', shares: 3000 },
    ])
  })

  it('clears cached account data and selection keys when the user changes', async () => {
    await cacheUser({ id: 'user-a', tier: 'group_creators' })
    await db.groups.put({
      id: 'group-a',
      name: 'A group',
      currency: '$',
      version: 1,
      updated_at: '2026-02-01T00:00:00.000Z',
    })
    await db.participants.put({
      id: 'pa',
      group_id: 'group-a',
      name: 'A',
      version: 1,
      updated_at: '2026-02-01T00:00:00.000Z',
    })
    await db.outbox.add(
      outboxRow({
        op_id: 'op-a',
        group_id: 'group-a',
        entity_type: 'group',
        entity_id: 'group-a',
        op_type: 'create',
      }),
    )
    await db.conflicts.add({
      op_id: 'op-a',
      group_id: 'group-a',
      entity_type: 'expense',
      entity_id: 'e-a',
      op_type: 'update',
      payload: {},
      created_at: '2026-02-01T00:00:00.000Z',
    })
    window.localStorage.setItem(
      'recentGroups',
      JSON.stringify([{ id: 'group-a', name: 'A group' }]),
    )
    window.localStorage.setItem('starredGroups', JSON.stringify(['group-a']))
    window.localStorage.setItem('group-a-activeUser', 'pa')
    window.localStorage.setItem('group-a-defaultSplittingOptions', '{}')

    await cacheUser({ id: 'user-b', tier: 'group_creators' })

    expect((await cachedUser()).id).toBe('user-b')
    expect(await db.groups.count()).toBe(0)
    expect(await db.participants.count()).toBe(0)
    expect(await db.outbox.count()).toBe(0)
    expect(await db.conflicts.count()).toBe(0)
    expect(window.localStorage.getItem('recentGroups')).toBeNull()
    expect(window.localStorage.getItem('starredGroups')).toBeNull()
    expect(window.localStorage.getItem('group-a-activeUser')).toBeNull()
    expect(window.localStorage.getItem('group-a-defaultSplittingOptions')).toBeNull()
  })

  it('only sends explicitly requested ids when syncing the group list', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    await db.groups.put({
      id: 'cached-only',
      name: 'Cached only',
      currency: '$',
      version: 1,
      updated_at: '2026-02-01T00:00:00.000Z',
    })
    const spy = vi.spyOn(onlineRepository.groups, 'sync').mockResolvedValue({
      is_authenticated: true,
      groups: [],
      user_groups: [],
    })
    await localRepository.groups.sync({ groupIds: [] })
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ groupIds: [] }),
      expect.anything(),
    )
  })

  it('does not send cached ids as claims for an authenticated list read', async () => {
    await cacheUser({ id: 'user-a', tier: 'group_creators' })
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    const spy = vi.spyOn(onlineRepository.groups, 'sync').mockResolvedValue({
      is_authenticated: true,
      groups: [{ id: 'g1', name: 'Trip', participants: [] }],
      user_groups: [],
    })

    await localRepository.groups.sync({ groupIds: ['g1'] })

    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ groupIds: [] }),
      expect.anything(),
    )
  })

  it('returns the documented GroupList envelope and honours ids/status', async () => {
    await db.groups.put({
      id: 'g2',
      name: 'Archived trip',
      currency: '$',
      version: 1,
      created_at: '2026-01-02T00:00:00.000Z',
      updated_at: '2026-01-02T00:00:00.000Z',
    })
    await db.userGroups.put({
      id: 'guest:g2',
      user_id: 'guest',
      group_id: 'g2',
      is_starred: false,
      is_archived: false,
      created_at: '2026-01-02T00:00:00.000Z',
      updated_at: '2026-01-02T00:00:00.000Z',
      version: 1,
    })
    await db.metadata.put({
      key: 'archivedGroups',
      value: ['g2'],
      updated_at: '2026-01-02T00:00:00.000Z',
    })

    const all = await localRepository.groups.list({ status: 'all' })
    expect(all).toMatchObject({ total: 2, limit: 50, offset: 0 })
    expect(all.items.map((/** @type {any} */ group) => group.id).sort()).toEqual(['g1', 'g2'])

    const onlyOne = await localRepository.groups.list({ ids: ['g1'] })
    expect(onlyOne.items.map((/** @type {any} */ group) => group.id)).toEqual(['g1'])

    const archived = await localRepository.groups.list({ status: 'archived' })
    expect(archived.items.map((/** @type {any} */ group) => group.id)).toEqual(['g2'])
  })

  it('removes local group data and selection keys when membership is removed', async () => {
    window.localStorage.setItem(
      'recentGroups',
      JSON.stringify([{ id: 'g1', name: 'Trip' }]),
    )
    window.localStorage.setItem('starredGroups', JSON.stringify(['g1']))
    window.localStorage.setItem('archivedGroups', JSON.stringify(['g1']))

    await localRepository.groups.removeMembership('g1')

    expect(await db.groups.get('g1')).toBeUndefined()
    expect(await db.expenses.count()).toBe(0)
    expect(await db.participants.count()).toBe(0)
    expect(window.localStorage.getItem('recentGroups')).toBe('[]')
    expect(window.localStorage.getItem('starredGroups')).toBe('[]')
    expect(window.localStorage.getItem('archivedGroups')).toBe('[]')
  })

  it('does not mark unchanged participants pending during a group update', async () => {
    const updated = await localRepository.groups.update('g1', {
      name: 'Renamed trip',
      participants: [
        { id: 'a', name: 'Alice' },
        { id: 'b', name: 'Bobby' },
      ],
    })
    expect(updated.name).toBe('Renamed trip')
    expect(await db.participants.get('a')).toMatchObject({ name: 'Alice', pending: false })
    expect(await db.participants.get('b')).toMatchObject({ name: 'Bobby', pending: true })
    const outbox = await db.outbox.toArray()
    expect(outbox.filter((row) => row.entity_type === 'participant')).toHaveLength(1)
  })

  it('computes recurring statistics from active heads, not materialized frames or the range', async () => {
    await db.expenses.bulkPut([
      {
        id: 'series-1',
        group_id: 'g1',
        expense_date: '2026-01-02',
        title: 'Rent',
        category_id: 0,
        amount: 100000,
        paid_by_id: 'a',
        is_reimbursement: false,
        split_mode: 'EVENLY',
        recurrence_rule: 'MONTHLY',
        is_recurring_head: false,
        created_at: '2026-01-02T10:00:00.000Z',
        updated_at: '2026-01-02T10:00:00.000Z',
        version: 1,
        deleted_at: null,
      },
      {
        id: 'series-2',
        group_id: 'g1',
        expense_date: '2026-02-02',
        title: 'Rent',
        category_id: 0,
        amount: 100000,
        paid_by_id: 'a',
        is_reimbursement: false,
        split_mode: 'EVENLY',
        recurrence_rule: 'MONTHLY',
        is_recurring_head: true,
        created_at: '2026-01-02T10:00:00.000Z',
        updated_at: '2026-02-02T10:00:00.000Z',
        version: 1,
        deleted_at: null,
      },
    ])
    for (const expenseId of ['series-1', 'series-2']) {
      await db.paidFor.bulkPut([
        { expense_id: expenseId, participant_id: 'a', shares: 1 },
        { expense_id: expenseId, participant_id: 'b', shares: 1 },
      ])
    }

    const full = await localRepository.stats.overview('g1')
    const ranged = await localRepository.stats.overview('g1', {
      from: '2026-02-01',
      to: '2026-02-28',
    })
    expect(full.recurring.count).toBe(1)
    expect(full.recurring.monthly_amount).toBe(100000)
    expect(ranged.recurring).toEqual(full.recurring)
  })

  it('exports the server CSV/JSON shape offline', async () => {
    const csv = await localRepository.exports.csv('g1')
    expect(csv.filename).toMatch(/^Spliit Export - Trip - \d{4}-\d{2}-\d{2}\.csv$/)
    expect(csv.content.startsWith('\ufeffDate,Description')).toBe(true)
    expect(csv.content).toContain('2026-01-02,Dinner,Groceries,USD,90.00,,,,No,Evenly,45,-45')
    const json = await localRepository.exports.json('g1')
    const parsed = JSON.parse(json.content)
    expect(parsed).toMatchObject({
      id: 'g1',
      name: 'Trip',
      currency_code: 'USD',
    })
    expect(parsed.expenses[0]).toMatchObject({
      id: 'e1',
      expense_date: '2026-01-02',
      category: { grouping: 'Food and Drink', name: 'Groceries' },
      amount: 9000,
      paid_for: [
        { participant_id: 'a', shares: 1 },
        { participant_id: 'b', shares: 1 },
      ],
    })
  })

  it('prunes local groups that are absent from an authenticated membership sync', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    await cacheUser({ id: 'user-a', tier: 'group_creators' })
    await db.userGroups.bulkPut([
      {
        id: 'user-a:g1',
        user_id: 'user-a',
        group_id: 'g1',
        is_starred: false,
        is_archived: false,
        version: 1,
        updated_at: '2026-02-01T00:00:00.000Z',
      },
      {
        id: 'user-a:gone',
        user_id: 'user-a',
        group_id: 'gone',
        is_starred: false,
        is_archived: false,
        version: 1,
        updated_at: '2026-02-01T00:00:00.000Z',
      },
    ])
    await db.groups.put({
      id: 'gone',
      name: 'Gone',
      currency: '$',
      version: 1,
      updated_at: '2026-02-01T00:00:00.000Z',
    })
    await db.expenses.put({
      id: 'gone-expense',
      group_id: 'gone',
      expense_date: '2026-02-01',
      title: 'Old',
      amount: 100,
      version: 1,
      created_at: '2026-02-01T00:00:00.000Z',
      updated_at: '2026-02-01T00:00:00.000Z',
      deleted_at: null,
    })
    vi.spyOn(onlineRepository.groups, 'sync').mockResolvedValue({
      is_authenticated: true,
      groups: [{ id: 'g1', name: 'Trip', participants: [] }],
      user_groups: [],
    })

    await localRepository.groups.sync({ groupIds: ['g1'] })

    expect(await db.groups.get('g1')).toBeTruthy()
    expect(await db.groups.get('gone')).toBeUndefined()
    expect(await db.expenses.get('gone-expense')).toBeUndefined()
  })

  it('keeps pending participants when the group list refreshes', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    await db.participants.put({
      id: 'p-local',
      group_id: 'g1',
      name: 'Pending participant',
      position: 2,
      version: 1,
      updated_at: '2026-02-01T00:00:00.000Z',
      pending: true,
    })
    vi.spyOn(onlineRepository.groups, 'sync').mockResolvedValue({
      is_authenticated: true,
      groups: [{ id: 'g1', name: 'Trip', participants: [] }],
      user_groups: [],
    })

    await localRepository.groups.sync({ groupIds: ['g1'] })

    expect(await db.participants.get('p-local')).toMatchObject({
      name: 'Pending participant',
      pending: true,
    })
  })

  it('keeps cached data when /me has no token, and clears it when refresh finds no session', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    await cacheUser({ id: 'user-a', tier: 'group_creators' })
    await db.groups.put({
      id: 'group-a',
      name: 'A group',
      currency: '$',
      version: 1,
      updated_at: '2026-02-01T00:00:00.000Z',
    })
    vi.spyOn(onlineRepository.auth, 'me').mockResolvedValue(null)
    vi.spyOn(onlineRepository.auth, 'refresh').mockResolvedValue(null)

    await expect(localRepository.auth.me()).resolves.toBeNull()
    // The login claimed the pre-existing guest group instead of dropping it;
    // group-a was added after the account became current.
    expect(await db.groups.count()).toBe(2)
    expect((await cachedUser()).id).toBe('user-a')

    await expect(localRepository.auth.refresh()).resolves.toBeNull()
    expect(await db.groups.count()).toBe(0)
    expect(await cachedUser()).toBeNull()
  })

  it('queues an offline receipt item create before its portion edit', async () => {
    const created = await localRepository.receipts.addItem('g1', 'r1', {
      name: 'Fries',
      quantity_milli: 1000,
      amount: 300,
      is_shared: true,
    })
    const item = created.items.find((/** @type {any} */ row) => row.name === 'Fries')
    expect(item.id).toMatch(/^ri_/)

    const updated = await localRepository.receipts.setPortions('g1', 'r1', item.id, [
      { target: 'PARTICIPANT', participant_id: 'a', quantity_milli: 1000 },
    ])
    const stored = updated.items.find((/** @type {any} */ row) => row.id === item.id)
    expect(stored.portions).toHaveLength(1)

    const outbox = await db.outbox.orderBy('seq').toArray()
    expect(outbox.map((row) => [row.entity_type, row.op_type])).toEqual([
      ['receipt_item', 'create'],
      ['receipt_portion', 'update'],
    ])
    expect(outbox[0].payload.id).toBe(item.id)
    expect(outbox[1].entity_id).toBe(item.id)
  })

  it('rejects online-only operations while offline', async () => {
    await expect(
      localRepository.receipts.extractTotal('g1', { image_url: '/uploads/x.jpg' }),
    ).rejects.toMatchObject({ code: 'offline_unsupported' })
    await expect(localRepository.admin.metrics()).rejects.toMatchObject({
      code: 'offline_unsupported',
    })
  })

  it('answers aborted reads with the aborted code', async () => {
    const controller = new AbortController()
    controller.abort()
    await expect(
      localRepository.expenses.list('g1', {}, { signal: controller.signal }),
    ).rejects.toMatchObject({ code: 'aborted' })
  })
})
