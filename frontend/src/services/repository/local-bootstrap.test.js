import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  api: {
    post: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
  },
}))

import { api } from '../api'
import { db } from '../db'
import { prefetchGroups } from '../sync'
import { localRepository, ready } from './local'

const get = /** @type {any} */ (api.get)

beforeEach(async () => {
  vi.clearAllMocks()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  await ready()
  await db.transaction('rw', db.tables, async () => {
    for (const table of db.tables) await table.clear()
  })
  await db.categories.bulkPut([
    { id: 0, grouping: 'Uncategorized', name: 'General' },
    { id: 9, grouping: 'Food and Drink', name: 'Groceries' },
  ])
})

/**
 * @param {string} groupId
 * @param {any[]} [expenses]
 * @returns {any}
 */
function snapshot(groupId, expenses = []) {
  return {
    cursor: 4,
    group: {
      id: groupId,
      name: `Group ${groupId}`,
      information: null,
      currency: '$',
      currency_code: 'USD',
      created_at: '2026-01-01T00:00:00.000Z',
      updated_at: '2026-01-01T00:00:00.000Z',
      version: 1,
      deleted_at: null,
      participants: [],
    },
    participants: [
      {
        id: 'a',
        name: 'Alice',
        group_id: groupId,
        updated_at: '2026-01-01T00:00:00.000Z',
        version: 1,
        deleted_at: null,
      },
      {
        id: 'b',
        name: 'Bob',
        group_id: groupId,
        updated_at: '2026-01-01T00:00:00.000Z',
        version: 1,
        deleted_at: null,
      },
    ],
    expenses,
    activities: [],
    receipts: [],
    categories: [],
  }
}

/**
 * @param {string} groupId
 * @returns {Promise<void>}
 */
async function seedListOnly(groupId) {
  await db.groups.put({
    id: groupId,
    name: `Group ${groupId}`,
    information: null,
    currency: '$',
    currency_code: 'USD',
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
    version: 1,
    deleted_at: null,
    list_only: true,
    cached_at: null,
  })
  await db.participants.bulkPut([
    {
      id: `p-${groupId}-a`,
      name: 'Alice',
      group_id: groupId,
      position: 0,
      updated_at: '2026-01-01T00:00:00.000Z',
      version: 1,
      deleted_at: null,
    },
  ])
}

describe('list-only group bootstrap', () => {
  it('bootstraps full data before serving expenses for a list-cache row', async () => {
    await seedListOnly('g1')
    get.mockResolvedValue(
      snapshot('g1', [
        {
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
          paid_for: [
            { participant_id: 'a', shares: 1 },
            { participant_id: 'b', shares: 1 },
          ],
          documents: [],
          receipt: null,
        },
      ]),
    )

    const listed = await localRepository.expenses.list('g1', { limit: 10 })

    expect(get).toHaveBeenCalledWith('/sync/bootstrap?group_id=g1')
    expect(listed.total).toBe(1)
    expect(listed.items[0].title).toBe('Dinner')
    expect(await db.groups.get('g1')).toMatchObject({ list_only: false })
    expect((await db.groups.get('g1')).cached_at).toBeTruthy()
  })

  it('prefetches every returned group, not only the five most recent', async () => {
    const ids = Array.from({ length: 7 }, (_, index) => `g${index + 1}`)
    for (const id of ids) await seedListOnly(id)
    get.mockImplementation((/** @type {string} */ path) => {
      const id = decodeURIComponent(String(path).split('group_id=')[1])
      return Promise.resolve(snapshot(id))
    })

    await prefetchGroups(ids)

    expect(get).toHaveBeenCalledTimes(7)
    for (const id of ids) {
      expect(await db.groups.get(id)).toMatchObject({ list_only: false })
    }
  })
})
