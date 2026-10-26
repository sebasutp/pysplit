import Dexie from 'dexie'
import { afterEach, describe, expect, it, vi } from 'vitest'

const V2_STORES = {
  groups: 'id, updated_at, version, deleted_at',
  participants: 'id, group_id, updated_at, version, deleted_at, position',
  expenses: 'id, group_id, expense_date, updated_at, version, deleted_at',
  paidFor: '[expense_id+participant_id], expense_id, participant_id',
  documents: 'id, expense_id, created_at',
  activities: 'id, group_id, time',
  receipts: 'id, group_id, expense_id, updated_at, version, deleted_at',
  receiptItems: 'id, receipt_id, position, updated_at, version, deleted_at',
  receiptPortions: 'id, item_id, updated_at, version, deleted_at',
  receiptOptOuts: 'id, receipt_id, participant_id, updated_at, version, deleted_at',
  categories: 'id',
  userGroups: 'id, user_id, group_id, [user_id+group_id], updated_at, version, deleted_at',
  outbox: '++seq, op_id, group_id, status, next_attempt_at',
  syncState: 'scope',
  conflicts: '++id, group_id, entity_type, entity_id, created_at',
  blobs: 'id, group_id',
  metadata: 'key',
}

/** @type {any} */
let loaded

afterEach(async () => {
  if (loaded?.db?.isOpen?.()) loaded.db.close()
  await Dexie.delete('pysplit')
  vi.unstubAllGlobals()
  vi.resetModules()
})

describe('Dexie schema updates', () => {
  it('opens a Stage 9 (v2) database without losing outbox or cached rows', async () => {
    const legacy = /** @type {any} */ (new Dexie('pysplit'))
    legacy.version(2).stores(V2_STORES)
    await legacy.open()
    await legacy.groups.put({
      id: 'g1',
      name: 'Old cached group',
      version: 1,
      updated_at: '2026-01-01T00:00:00.000Z',
    })
    await legacy.outbox.add({
      op_id: 'op1',
      group_id: 'g1',
      entity_type: 'expense',
      entity_id: 'e1',
      op_type: 'create',
      payload: { title: 'Pending lunch' },
      status: 'pending',
      attempts: 0,
      next_attempt_at: '2026-01-01T00:00:00.000Z',
      created_at: '2026-01-01T00:00:00.000Z',
      updated_at: '2026-01-01T00:00:00.000Z',
    })
    await legacy.metadata.put({ key: 'session_user', value: { id: 'user-a' } })
    legacy.close()

    vi.resetModules()
    loaded = await import('./db')
    await expect(loaded.verifyDatabaseCompatibility()).resolves.toMatchObject({
      version: 3,
    })

    expect(await loaded.db.groups.get('g1')).toMatchObject({ name: 'Old cached group' })
    expect(await loaded.db.outbox.count()).toBe(1)
    expect(await loaded.db.outbox.toArray()).toEqual([
      expect.objectContaining({ op_id: 'op1', status: 'pending' }),
    ])
    expect((await loaded.db.metadata.get('session_user'))?.value).toEqual({ id: 'user-a' })

    const blobIndexes = loaded.db.blobs.schema.indexes.map(
      (/** @type {any} */ index) => index.name,
    )
    expect(blobIndexes).toEqual(expect.arrayContaining(['group_id', 'kind', 'entity_id']))
  })

  it('accepts the emitted build contract and rejects an older or narrower one', async () => {
    loaded = await import('./db')
    const contract = loaded.DATABASE_BUILD_CONTRACT

    await expect(loaded.verifyIncomingBuildCompatibility(contract)).resolves.toEqual({
      version: 3,
      incomingVersion: 3,
    })
    await expect(
      loaded.verifyIncomingBuildCompatibility({ ...contract, schemaVersion: 2 }),
    ).rejects.toThrow('older than local')
    await expect(
      loaded.verifyIncomingBuildCompatibility({
        ...contract,
        requiredTables: contract.requiredTables.filter(
          (/** @type {string} */ name) => name !== 'outbox',
        ),
      }),
    ).rejects.toThrow('drops Dexie tables: outbox')
    await expect(
      loaded.verifyIncomingBuildCompatibility({
        ...contract,
        requiredIndexes: { ...contract.requiredIndexes, outbox: [] },
      }),
    ).rejects.toThrow('drops Dexie indexes')
  })

  it('fetches the waiting build contract without using the HTTP cache', async () => {
    loaded = await import('./db')
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => loaded.DATABASE_BUILD_CONTRACT,
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(loaded.fetchIncomingBuildContract()).resolves.toEqual(
      loaded.DATABASE_BUILD_CONTRACT,
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/pwa-build.json',
      expect.objectContaining({ cache: 'no-store' }),
    )
  })
})
