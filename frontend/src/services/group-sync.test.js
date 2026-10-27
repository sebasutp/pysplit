import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { db, getMetadata, setMetadata } from './db'
import { stopSync } from './sync'
import { onlineRepository } from './repository/online'
import {
  cacheUser,
  cachedUser,
  localRepository,
  reconcilePendingGroupMerge,
  ready,
} from './repository/local'

/** @param {boolean} value */
function online(value) {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value })
}

async function clearDatabase() {
  await db.transaction('rw', db.tables, async () => {
    for (const table of db.tables) await table.clear()
  })
}

async function seedGuestCache() {
  await db.groups.bulkPut([
    {
      id: 'g1',
      name: 'Trip',
      currency: '$',
      version: 1,
      updated_at: '2026-10-01T00:00:00.000Z',
      deleted_at: null,
    },
    {
      id: 'g2',
      name: 'Flat',
      currency: '$',
      version: 1,
      updated_at: '2026-10-01T00:00:00.000Z',
      deleted_at: null,
    },
  ])
  await db.participants.bulkPut([
    {
      id: 'p1',
      name: 'Alice',
      group_id: 'g1',
      position: 0,
      version: 1,
      updated_at: '2026-10-01T00:00:00.000Z',
    },
  ])
  await db.expenses.put({
    id: 'e1',
    group_id: 'g1',
    expense_date: '2026-10-01',
    title: 'Dinner',
    category_id: 0,
    amount: 1000,
    paid_by_id: 'p1',
    split_mode: 'EVENLY',
    recurrence_rule: 'NONE',
    version: 1,
    created_at: '2026-10-01T00:00:00.000Z',
    updated_at: '2026-10-01T00:00:00.000Z',
  })
  await setMetadata('recentGroups', [
    { id: 'g1', name: 'Trip' },
    { id: 'g2', name: 'Flat' },
  ])
  await setMetadata('starredGroups', ['g1'])
  await setMetadata('archivedGroups', ['g2'])
}

beforeEach(async () => {
  online(false)
  await ready()
  window.localStorage.clear()
  await clearDatabase()
  await seedGuestCache()
  await db.categories.put({ id: 0, grouping: 'Uncategorized', name: 'General' })
})

afterEach(async () => {
  await stopSync()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('authenticated group merge', () => {
  it('claims guest groups and preferences without clearing the guest cache', async () => {
    await cacheUser({ id: 'user-a', tier: 'group_creators' })

    expect((await cachedUser())?.id).toBe('user-a')
    // The cached groups and their expenses survive the login.
    expect(await db.groups.count()).toBe(2)
    expect(await db.expenses.get('e1')).toMatchObject({ title: 'Dinner' })

    const memberships = await db.userGroups.toArray()
    expect(memberships).toHaveLength(2)
    expect(
      memberships.find((row) => row.group_id === 'g1'),
    ).toMatchObject({ user_id: 'user-a', is_starred: true, is_archived: false })
    expect(
      memberships.find((row) => row.group_id === 'g2'),
    ).toMatchObject({ user_id: 'user-a', is_starred: false, is_archived: true })

    const marker = await getMetadata('pending_group_merge')
    expect(marker).toMatchObject({
      user_id: 'user-a',
      group_ids: expect.arrayContaining(['g1', 'g2']),
    })

    const operations = await db.outbox.toArray()
    const claims = operations.filter((row) => row.entity_type === 'user_group')
    expect(claims.map((row) => row.entity_id).sort()).toEqual(['g1', 'g2'])
    // Guest preferences are positive-only: a member without an existing
    // membership must not send `false` for the other flag, which could clobber
    // a choice made on another device.
    expect(claims.find((row) => row.entity_id === 'g1')?.payload).toEqual({
      is_starred: true,
    })
    expect(claims.find((row) => row.entity_id === 'g2')?.payload).toEqual({
      is_archived: true,
    })
  })

  it('queues the merge offline and reconciles it when the API returns', async () => {
    await cacheUser({ id: 'user-a', tier: 'group_creators' })
    expect(await reconcilePendingGroupMerge()).toBeNull()
    expect(await getMetadata('pending_group_merge')).toBeTruthy()

    online(true)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline prefetch')))
    const sync = vi.spyOn(onlineRepository.groups, 'sync').mockResolvedValue({
      is_authenticated: true,
      isAuthenticated: true,
      groups: [
        { id: 'g1', name: 'Trip' },
        { id: 'g2', name: 'Flat' },
      ],
      user_groups: [],
    })

    const result = await reconcilePendingGroupMerge()

    expect(result?.is_authenticated).toBe(true)
    expect(sync).toHaveBeenCalledWith({
      groupIds: expect.arrayContaining(['g1', 'g2']),
      claimGroupIds: true,
      starredGroupIds: ['g1'],
      archivedGroupIds: ['g2'],
    })
    expect(await getMetadata('pending_group_merge')).toBeNull()
    // Reconciliation updates the same rows instead of duplicating the guest
    // cache or the account memberships.
    expect(await db.groups.count()).toBe(2)
    expect(await db.userGroups.count()).toBe(2)
  })

  it('keeps a queued guest group and its offline writes when a list response is stale', async () => {
    await cacheUser({ id: 'user-a', tier: 'group_creators' })
    online(true)
    vi.spyOn(onlineRepository.groups, 'sync').mockResolvedValue({
      is_authenticated: true,
      isAuthenticated: true,
      // The server scope has not caught up with the queued claim yet.
      groups: [],
      user_groups: [],
    })

    await localRepository.groups.sync({ groupIds: [] })

    expect(await db.groups.get('g1')).toMatchObject({ name: 'Trip' })
    expect(await db.expenses.get('e1')).toMatchObject({ title: 'Dinner' })
    const claims = (await db.outbox.toArray()).filter(
      (row) => row.entity_type === 'user_group' && row.entity_id === 'g1',
    )
    expect(claims).toHaveLength(1)
  })

  it('keeps the login merge pending until the request succeeds', async () => {
    await cacheUser({ id: 'user-a', tier: 'group_creators' })
    online(true)
    vi.spyOn(onlineRepository.groups, 'sync').mockRejectedValue(
      Object.assign(new Error('unavailable'), { code: 'network' }),
    )

    expect(await reconcilePendingGroupMerge()).toBeNull()
    expect(await getMetadata('pending_group_merge')).toMatchObject({ user_id: 'user-a' })
  })
})
