import { beforeEach, describe, expect, it, vi } from 'vitest'

import { exportBackup, importBackup } from './backup'
import { db } from './db'
import { MIGRATION_VERSION, migrateLocalStorage } from './local-storage-migration'
import { cacheUser } from './repository/local'

async function clearMetadata() {
  await db.transaction('rw', db.tables, async () => {
    for (const table of db.tables) await table.clear()
  })
}

beforeEach(async () => {
  await clearMetadata()
  window.localStorage.clear()
})

describe('localStorage migration', () => {
  it('copies the reference preference keys into Dexie once', async () => {
    window.localStorage.setItem(
      'recentGroups',
      JSON.stringify([{ id: 'g1', name: 'Trip' }]),
    )
    window.localStorage.setItem('starredGroups', JSON.stringify(['g1']))
    window.localStorage.setItem('archivedGroups', JSON.stringify([]))
    window.localStorage.setItem('g1-activeUser', 'p1')
    window.localStorage.setItem('g1-newUser', 'p2')
    window.localStorage.setItem('newGroup-activeUser', 'None')
    window.localStorage.setItem(
      'g1-defaultSplittingOptions',
      JSON.stringify({ splitMode: 'BY_SHARES', paidFor: [] }),
    )

    await expect(migrateLocalStorage()).resolves.toBe(true)
    await expect(migrateLocalStorage()).resolves.toBe(false)

    expect(await db.metadata.get('migrated_from_localstorage')).toMatchObject({
      value: MIGRATION_VERSION,
    })
    expect((await db.metadata.get('recentGroups')).value).toEqual([
      { id: 'g1', name: 'Trip' },
    ])
    expect((await db.metadata.get('starredGroups')).value).toEqual(['g1'])
    expect((await db.metadata.get('activeUser')).value).toEqual({ g1: 'p1' })
    expect((await db.metadata.get('newUser')).value).toEqual({ g1: 'p2' })
    expect((await db.metadata.get('newGroupActiveUser')).value).toBe('None')
    expect((await db.metadata.get('defaultSplittingOptions')).value).toEqual({
      g1: { splitMode: 'BY_SHARES', paidFor: [] },
    })
  })
})

describe('JSON backup', () => {
  it('round-trips cached tables and the pending outbox', async () => {
    await db.groups.put({ id: 'g1', name: 'Trip', version: 1, updated_at: 'now' })
    await db.outbox.put({
      seq: 1,
      op_id: 'op1',
      group_id: 'g1',
      entity_type: 'expense',
      entity_id: 'e1',
      op_type: 'create',
      payload: { title: 'Lunch' },
      status: 'pending',
      attempts: 0,
      next_attempt_at: 'now',
      created_at: 'now',
      updated_at: 'now',
    })

    const backup = await exportBackup()
    expect(backup.version).toBe(1)
    expect(backup.tables.groups).toHaveLength(1)

    await clearMetadata()
    await importBackup(backup)

    expect((await db.groups.get('g1')).name).toBe('Trip')
    expect((await db.outbox.toArray())[0]).toMatchObject({
      op_id: 'op1',
      status: 'pending',
    })
  })

  it('preserves the live session and resets the sync cursor on restore', async () => {
    await db.metadata.put({
      key: 'session_user',
      value: { id: 'user-a', tier: 'admin' },
      updated_at: 'now',
    })
    await db.syncState.put({ scope: 'user:user-a', cursor: 42, updated_at: 'now' })
    const backup = await exportBackup()
    expect(backup.owner).toBe('user-a')

    await db.metadata.put({
      key: 'session_user',
      value: { id: 'user-a', tier: 'admin' },
      updated_at: 'later',
    })
    await db.syncState.put({ scope: 'user:user-a', cursor: 99, updated_at: 'later' })
    await db.metadata.put({
      key: 'session_user',
      value: { id: 'user-a', tier: 'admin' },
      updated_at: 'now',
    })
    await db.metadata.put({
      key: 'session_user_cached_at',
      value: 'now',
      updated_at: 'now',
    })

    await importBackup(backup)

    expect((await db.metadata.get('session_user'))?.value.id).toBe('user-a')
    expect(await db.syncState.count()).toBe(0)
  })

  it('rejects a backup from another account', async () => {
    await db.metadata.put({
      key: 'session_user',
      value: { id: 'user-a', tier: 'admin' },
      updated_at: 'now',
    })
    const backup = await exportBackup()

    await db.metadata.put({
      key: 'session_user',
      value: { id: 'user-b', tier: 'admin' },
      updated_at: 'now',
    })

    await expect(importBackup(backup)).rejects.toThrow('different account')
  })

  it('round-trips blob payloads', async () => {
    const blob = new Blob(['hello'], { type: 'text/plain' })
    // fake-indexeddb cannot structured-clone jsdom Blobs, so exercise the
    // export/import conversion directly.
    const toArray = vi.spyOn(db.blobs, 'toArray').mockResolvedValue([
      { id: 'blob-1', group_id: 'g1', data: blob },
    ])

    const backup = await exportBackup()
    expect(backup.blobs[0].data_base64).toBe(btoa('hello'))
    toArray.mockRestore()

    await clearMetadata()
    const put = /** @type {any} */ (vi.spyOn(db.blobs, 'put')).mockResolvedValue(undefined)
    await importBackup(backup)

    const restored = /** @type {any} */ (put.mock.calls[0][0])
    expect(restored.data).toBeInstanceOf(Blob)
    expect(await restored.data.text()).toBe('hello')
    put.mockRestore()
  })

  it('keeps a logged-in session usable after restore and reload', async () => {
    await db.metadata.put({
      key: 'session_user',
      value: { id: 'user-a', tier: 'admin' },
      updated_at: 'now',
    })
    await db.groups.put({ id: 'g1', name: 'Restored', version: 1, updated_at: 'now' })
    const backup = await exportBackup()

    await importBackup(backup)
    // Simulate the reload boot path: cacheUser with the same account must not
    // treat the restore as an account switch and clear the data.
    await cacheUser({ id: 'user-a', tier: 'admin' })

    expect((await db.groups.get('g1'))?.name).toBe('Restored')
  })

  it('rejects an unknown backup version', async () => {
    await expect(importBackup({ version: 99 })).rejects.toThrow('Unsupported backup version')
  })
})
