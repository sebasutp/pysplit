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

const serverAttachment = {
  id: 'att-server',
  group_id: 'g1',
  expense_id: 'e1',
  url: 'https://files.example/scan.png',
  thumbnail_url: 'https://files.example/scan.png',
  filename: 'scan.png',
  content_type: 'image/png',
  byte_size: 4,
  width: 10,
  height: 20,
  receipt_status: 'EXTRACTED',
  attempts: 1,
  merchant: 'Corner Shop',
  receipt_date: '2026-02-01',
  currency_code: 'USD',
  total: 1000,
  provider: 'openai-compatible',
  model: 'mock',
  created_at: '2026-02-01T10:00:00.000Z',
  updated_at: '2026-02-01T10:00:00.000Z',
  version: 2,
  deleted_at: null,
}

const serverItem = {
  id: 'ai1',
  attachment_id: 'att-server',
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

describe('queued attachments', () => {
  it('stores an offline attachment as a placeholder plus a blob outbox row', async () => {
    const attachment = await localRepository.attachments.upload(
      'g1',
      fakeFile('receipt.png', 'image/png'),
      { width: 12, height: 24, expense_id: 'e1' },
    )

    expect(attachment).toMatchObject({
      width: 12,
      height: 24,
      expense_id: 'e1',
      pending: true,
      pending_upload: true,
    })
    expect(await db.attachments.get(attachment.id)).toMatchObject({ pending_upload: true })
    expect(await db.blobs.count()).toBe(1)
    const [operation] = await db.outbox.toArray()
    expect(operation).toMatchObject({
      entity_type: 'attachment_upload',
      transport: 'blob',
      status: 'pending',
    })
    expect(operation.meta.blob_id).toBeTruthy()
  })

  it('uploads a queued attachment and replaces the placeholder', async () => {
    const attachment = await localRepository.attachments.upload(
      'g1',
      fakeFile('receipt.png', 'image/png'),
      { width: 12, height: 24, expense_id: 'e1' },
    )
    await stopSync()
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    post.mockResolvedValue({
      ...serverAttachment,
      id: 'att-server',
      receipt_status: null,
      merchant: null,
      total: null,
    })

    await pushPending({ ignoreBackoff: true })

    expect(post).toHaveBeenCalledWith(
      '/groups/g1/attachments',
      expect.objectContaining({ body: expect.any(FormData) }),
    )
    expect(await db.attachments.get(attachment.id)).toBeUndefined()
    expect(await db.attachments.get('att-server')).toMatchObject({
      expense_id: 'e1',
      pending: false,
    })
    expect(await db.blobs.count()).toBe(0)
    expect(await db.outbox.count()).toBe(0)
  })

  it('queues a total-only scan while offline', async () => {
    const attachment = await localRepository.attachments.upload(
      'g1',
      fakeFile('scan.png', 'image/png'),
      { width: 10, height: 20 },
    )
    const result = await localRepository.attachments.extractTotal('g1', attachment.id)
    expect(result.pending).toBe(true)
    const [queued] = await db.outbox.toArray()
    expect(queued.payload.mode).toBe('total')
  })

  it('records an expense link supplied when extraction is requested offline', async () => {
    const image = await localRepository.attachments.upload(
      'g1',
      fakeFile('scan.png', 'image/png'),
      { width: 10, height: 20 },
    )
    const state = await localRepository.attachments.extractItems('g1', image.id, {
      expense_id: 'e1',
    })

    expect(state.attachment).toMatchObject({ pending_scan: true, expense_id: 'e1' })
    const [queued] = await db.outbox.toArray()
    expect(queued.payload).toMatchObject({ mode: 'items', expense_id: 'e1' })
  })

  it('keeps a queued scan pending and completes it after reconnect', async () => {
    const image = await localRepository.attachments.upload(
      'g1',
      fakeFile('scan.png', 'image/png'),
      { width: 10, height: 20, expense_id: 'e1' },
    )
    const state = await localRepository.attachments.extractItems('g1', image.id)
    expect(state.attachment).toMatchObject({
      receipt_status: 'PENDING',
      pending_scan: true,
      expense_id: 'e1',
    })
    expect(state.items).toEqual([])

    await stopSync()
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    post.mockImplementation((/** @type {string} */ path) => {
      if (path.endsWith('/attachments')) {
        return Promise.resolve({ ...serverAttachment, receipt_status: 'PENDING' })
      }
      if (path.endsWith('/extract-items')) {
        return Promise.resolve({
          status: 'EXTRACTED',
          attachment_id: 'att-server',
          attachment: serverAttachment,
          items: [serverItem],
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
      attachments: [
        {
          attachment: serverAttachment,
          items: [serverItem],
          portions: [],
          opt_outs: [
            {
              id: 'att-server:b',
              attachment_id: 'att-server',
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
      '/groups/g1/attachments/att-server/extract-items',
      expect.objectContaining({
        body: expect.objectContaining({ expense_id: 'e1' }),
      }),
    )
    expect(await db.attachments.get(image.id)).toBeUndefined()
    expect(await db.attachments.get('att-server')).toMatchObject({
      receipt_status: 'EXTRACTED',
      expense_id: 'e1',
    })
    expect(await db.attachmentItems.get('ai1')).toMatchObject({ name: 'Pizza' })
    expect(await db.attachmentOptOuts.get('att-server:b')).toMatchObject({
      participant_id: 'b',
    })
    await expect(
      localRepository.attachments.get('g1', { expense_id: 'e1' }),
    ).resolves.toMatchObject({ attachment: { id: 'att-server', expense_id: 'e1' } })
    expect(await db.blobs.count()).toBe(0)
    expect(await db.outbox.count()).toBe(0)
  })
})
