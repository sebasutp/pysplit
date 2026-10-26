import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
  },
}))

import { api } from './api'
import { db, readCursor, writeCursor } from './db'
import { outboxRow, pendingCount } from './outbox'
import { discardFailed, pullChanges, pushPending } from './sync'

const post = /** @type {any} */ (api.post)
const get = /** @type {any} */ (api.get)

beforeEach(async () => {
  vi.clearAllMocks()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  await db.transaction('rw', db.tables, async () => {
    for (const table of db.tables) await table.clear()
  })
})

describe('pull cursor recovery', () => {
  it('batches more than 500 group ids instead of breaking the request cap', async () => {
    for (let index = 0; index < 501; index += 1) {
      await db.groups.put({ id: `g${index}`, name: `Group ${index}`, version: 1 })
    }
    post.mockImplementation((/** @type {string} */ _path, /** @type {any} */ options) =>
      Promise.resolve({
        changes: [],
        cursor: options.body.cursor,
        has_more: false,
      }),
    )

    await pullChanges()

    const pulls = post.mock.calls.filter((/** @type {any} */ call) => call[0] === '/sync/pull')
    expect(pulls.map((/** @type {any} */ call) => call[1].body.group_ids.length)).toEqual([500, 1])
  })

  it('converges on the highest snapshot cursor and drops groups the server lost', async () => {
    await db.groups.put({ id: 'g1', name: 'Trip', version: 1 })
    await db.groups.put({ id: 'g2', name: 'Gone', version: 1 })
    await writeCursor('guest', 5)

    post.mockRejectedValueOnce(
      Object.assign(new Error('bootstrap required'), { code: 'conflict' }),
    )
    get.mockImplementation((/** @type {string} */ path) => {
      if (String(path).includes('g2')) {
        return Promise.reject(Object.assign(new Error('group not found'), { code: 'not_found' }))
      }
      return Promise.resolve({
        cursor: 10,
        group: { id: 'g1', name: 'Trip', version: 2 },
        participants: [],
        expenses: [],
        activities: [],
        receipts: [],
        categories: [],
      })
    })

    await pullChanges()

    expect(await readCursor('guest')).toBe(10)
    expect(await db.groups.get('g2')).toBeUndefined()
    const group = await db.groups.get('g1')
    expect(group).toMatchObject({ id: 'g1', name: 'Trip', version: 2, list_only: false })
    expect(group.cached_at).toBeTruthy()
    expect(get).toHaveBeenCalledTimes(2)

    post.mockResolvedValueOnce({ changes: [], cursor: 10, has_more: false })
    await pullChanges()

    expect(get).toHaveBeenCalledTimes(2)
    expect(post.mock.calls.at(-1)[1].body.cursor).toBe(10)
  })
})

describe('forced push', () => {
  it('clears participant pending flags after a flat group-create push result', async () => {
    await db.groups.put({
      id: 'g1',
      name: 'Trip',
      version: 1,
      updated_at: '2026-01-01T00:00:00.000Z',
      pending: true,
    })
    await db.participants.put({
      id: 'p1',
      group_id: 'g1',
      name: 'Alice',
      position: 0,
      version: 1,
      updated_at: '2026-01-01T00:00:00.000Z',
      pending: true,
    })
    await db.outbox.add(
      outboxRow({
        op_id: 'op-group',
        group_id: 'g1',
        entity_type: 'group',
        entity_id: 'g1',
        op_type: 'create',
      }),
    )
    post.mockResolvedValueOnce({
      results: [
        {
          op_id: 'op-group',
          status: 'applied',
          entity: {
            id: 'g1',
            name: 'Trip',
            version: 1,
            participants: [
              {
                id: 'p1',
                name: 'Alice',
                group_id: 'g1',
                version: 1,
                updated_at: '2026-01-01T00:00:00.000Z',
              },
            ],
          },
        },
      ],
    })

    await pushPending()

    expect(await db.groups.get('g1')).toMatchObject({ pending: false })
    expect(await db.participants.get('p1')).toMatchObject({ pending: false })
  })

  it('removes the local entity when a failed create is discarded', async () => {
    await db.expenses.put({
      id: 'ghost',
      group_id: 'g1',
      expense_date: '2026-01-02',
      title: 'Ghost',
      amount: 100,
      version: 1,
      deleted_at: null,
      pending: true,
    })
    await db.outbox.add({
      ...outboxRow({
        op_id: 'op-ghost',
        group_id: 'g1',
        entity_type: 'expense',
        entity_id: 'ghost',
        op_type: 'create',
      }),
      seq: 1,
      status: 'failed',
    })

    await discardFailed()

    expect(await db.expenses.get('ghost')).toBeUndefined()
    expect(await db.outbox.count()).toBe(0)
  })

  it('stops after a full batch that made no progress instead of retrying forever', async () => {
    for (let index = 0; index < 50; index += 1) {
      await db.outbox.add(
        outboxRow({
          op_id: `op-${index}`,
          group_id: 'g1',
          entity_type: 'expense',
          entity_id: `e-${index}`,
          op_type: 'update',
        }),
      )
    }
    post.mockImplementation((/** @type {string} */ path, /** @type {any} */ options) => {
      if (path !== '/sync/push') return Promise.resolve({})
      return Promise.resolve({
        results: options.body.operations.map((/** @type {any} */ operation) => ({
          op_id: operation.op_id,
          status: 'error',
          code: 'server',
          detail: 'temporary failure',
        })),
      })
    })

    await pushPending({ ignoreBackoff: true })

    const pushes = post.mock.calls.filter((/** @type {any} */ call) => call[0] === '/sync/push')
    expect(pushes).toHaveLength(1)
    expect(await pendingCount()).toBe(50)
  })
})
