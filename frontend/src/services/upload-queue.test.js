import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import { api } from './api'
import { db } from './db'
import { localRepository, ready } from './repository/local'
import { pushPending, stopSync } from './sync'

const post = /** @type {any} */ (api.post)
const get = /** @type {any} */ (api.get)

/** @param {string} name @param {string} type */
function fakeFile(name, type) {
  return {
    name,
    type,
    arrayBuffer: async () => new Uint8Array([1, 2, 3, 4]).buffer,
  }
}

async function seedGroup() {
  await db.groups.put({
    id: 'g1',
    name: 'Trip',
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
      group_id: 'g1',
      name: 'Alice',
      position: 0,
      created_at: '2026-01-01T00:00:00.000Z',
      updated_at: '2026-01-01T00:00:00.000Z',
      version: 1,
      deleted_at: null,
    },
    {
      id: 'b',
      group_id: 'g1',
      name: 'Bob',
      position: 1,
      created_at: '2026-01-01T00:00:00.000Z',
      updated_at: '2026-01-01T00:00:00.000Z',
      version: 1,
      deleted_at: null,
    },
  ])
}

beforeEach(async () => {
  await ready()
  await db.transaction('rw', db.tables, async () => {
    for (const table of db.tables) await table.clear()
  })
  await seedGroup()
  vi.clearAllMocks()
  Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
})

afterEach(async () => {
  await stopSync()
  vi.restoreAllMocks()
})

describe('queued uploads', () => {
  it('stores an offline document as a placeholder plus a blob outbox row', async () => {
    const document = await localRepository.documents.upload(
      'g1',
      'e1',
      fakeFile('receipt.png', 'image/png'),
      { width: 12, height: 24 },
    )

    expect(document).toMatchObject({
      width: 12,
      height: 24,
      expense_id: 'e1',
      pending: true,
      pending_upload: true,
    })
    expect(await db.documents.get(document.id)).toMatchObject({ pending_upload: true })
    expect(await db.blobs.count()).toBe(1)

    const [operation] = await db.outbox.toArray()
    expect(operation).toMatchObject({
      entity_type: 'document_upload',
      transport: 'blob',
      status: 'pending',
    })
    expect(operation.meta.blob_id).toBeTruthy()
  })

  it('uploads a queued document and replaces the placeholder with the server row', async () => {
    const document = await localRepository.documents.upload(
      'g1',
      'e1',
      fakeFile('receipt.png', 'image/png'),
      { width: 12, height: 24 },
    )
    await stopSync()
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    post.mockResolvedValue({
      id: 'doc-server',
      url: '/api/groups/g1/expenses/e1/documents/doc-server',
      width: 12,
      height: 24,
    })

    await pushPending({ ignoreBackoff: true })

    expect(post).toHaveBeenCalledWith(
      '/groups/g1/expenses/e1/documents',
      expect.objectContaining({ body: expect.any(FormData) }),
    )
    expect(await db.documents.get(document.id)).toBeUndefined()
    expect(await db.documents.get('doc-server')).toMatchObject({
      expense_id: 'e1',
      pending: false,
    })
    expect(await db.blobs.count()).toBe(0)
    expect(await db.outbox.count()).toBe(0)
  })

  it('records an expense link supplied when extraction is requested offline', async () => {
    const image = await localRepository.receipts.upload(
      'g1',
      fakeFile('scan.png', 'image/png'),
      { width: 10, height: 20 },
    )
    const state = await localRepository.receipts.extractItems('g1', {
      image_url: image.url,
      image_width: 10,
      image_height: 20,
      expense_id: 'e1',
    })

    expect(state.receipt).toMatchObject({ pending_scan: true, expense_id: 'e1' })
    const [queued] = await db.outbox.toArray()
    expect(queued.payload).toMatchObject({ mode: 'items', expense_id: 'e1' })
  })

  it('keeps a queued receipt scan pending and completes it after reconnect', async () => {
    const image = await localRepository.receipts.upload(
      'g1',
      fakeFile('scan.png', 'image/png'),
      { width: 10, height: 20, expense_id: 'e1' },
    )
    expect(image.pending).toBe(true)

    const state = await localRepository.receipts.extractItems('g1', {
      image_url: image.url,
      image_width: 10,
      image_height: 20,
    })
    expect(state.receipt).toMatchObject({
      status: 'PENDING',
      pending_scan: true,
      expense_id: 'e1',
    })
    expect(state.items).toEqual([])

    const [queued] = await db.outbox.toArray()
    expect(queued.payload.mode).toBe('items')

    await stopSync()
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    const receipt = {
      id: 'r-server',
      group_id: 'g1',
      image_url: 'https://files.example/scan.png',
      image_width: 10,
      image_height: 20,
      status: 'EXTRACTED',
      attempts: 1,
      merchant: 'Corner Shop',
      receipt_date: '2026-02-01',
      currency_code: 'USD',
      total: 1000,
      expense_id: null,
      created_at: '2026-02-01T10:00:00.000Z',
      updated_at: '2026-02-01T10:00:00.000Z',
      version: 2,
      deleted_at: null,
    }
    const item = {
      id: 'ri1',
      receipt_id: 'r-server',
      name: 'Pizza',
      quantity_milli: 1000,
      unit_price: 1000,
      amount: 1000,
      is_shared: true,
      is_adjustment: false,
      position: 0,
      created_at: '2026-02-01T10:00:00.000Z',
      updated_at: '2026-02-01T10:00:00.000Z',
      version: 1,
      deleted_at: null,
      portions: [],
    }
    post.mockImplementation((/** @type {string} */ path) => {
      if (path.endsWith('/receipts/upload')) {
        return Promise.resolve({
          url: 'https://files.example/scan.png',
          width: 10,
          height: 20,
        })
      }
      if (path.endsWith('/receipts/extract-items')) {
        return Promise.resolve({
          status: 'EXTRACTED',
          receipt_id: 'r-server',
          receipt: { ...receipt, expense_id: 'e1' },
          items: [item],
          opt_outs: ['b'],
          split: {},
        })
      }
      return Promise.reject(new Error(`unexpected ${path}`))
    })
    get.mockResolvedValue({
      cursor: 5,
      group: { id: 'g1', name: 'Trip', version: 1 },
      participants: [
        { id: 'a', name: 'Alice', group_id: 'g1', version: 1 },
        { id: 'b', name: 'Bob', group_id: 'g1', version: 1 },
      ],
      expenses: [],
      activities: [],
      receipts: [
        {
          receipt: { ...receipt, expense_id: 'e1' },
          items: [item],
          portions: [],
          opt_outs: [
            {
              id: 'r-server:b',
              receipt_id: 'r-server',
              participant_id: 'b',
              created_at: '2026-02-01T10:00:00.000Z',
              updated_at: '2026-02-01T10:00:00.000Z',
              version: 1,
              deleted_at: null,
            },
          ],
        },
      ],
      categories: [],
    })

    await pushPending({ ignoreBackoff: true })

    expect(post).toHaveBeenCalledWith(
      '/groups/g1/receipts/extract-items',
      expect.objectContaining({
        body: expect.objectContaining({
          expense_id: 'e1',
          image_url: 'https://files.example/scan.png',
        }),
      }),
    )
    expect(await db.receipts.get(image.receipt_id)).toBeUndefined()
    expect(await db.receipts.get('r-server')).toMatchObject({
      status: 'EXTRACTED',
      expense_id: 'e1',
    })
    expect((await db.receipts.get('r-server')).pending_scan).toBeFalsy()
    expect(await db.receiptItems.get('ri1')).toMatchObject({ name: 'Pizza' })
    expect(await db.receiptOptOuts.get('r-server:b')).toMatchObject({
      participant_id: 'b',
    })
    // The post-push bootstrap must keep the link visible to the expense page.
    await expect(
      localRepository.receipts.get('g1', { expense_id: 'e1' }),
    ).resolves.toMatchObject({
      receipt: { id: 'r-server', expense_id: 'e1' },
    })
    expect(await db.blobs.count()).toBe(0)
    expect(await db.outbox.count()).toBe(0)
  })
})
