// @ts-nocheck
// Dexie tables are untyped at runtime; the repository contract tests cover shapes.
/**
 * User-triggered, versioned JSON backup and restore.
 *
 * The backup includes local groups, expenses, preferences, the outbox and
 * conflict records. Pending blobs are encoded as base64 when the browser can
 * read them, so a restore on the same profile keeps queued uploads.
 */

import { db, getMetadata, nowIso } from './db'

export const BACKUP_VERSION = 1

const SESSION_METADATA_KEYS = new Set(['session_user', 'session_user_cached_at'])

const TABLES = [
  'groups',
  'participants',
  'expenses',
  'paidFor',
  'documents',
  'activities',
  'receipts',
  'receiptItems',
  'receiptPortions',
  'receiptOptOuts',
  'categories',
  'userGroups',
  'outbox',
  'syncState',
  'conflicts',
  'metadata',
]

/**
 * @param {Blob} blob
 * @returns {Promise<string>}
 */
function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || '')
      resolve(result.slice(result.indexOf(',') + 1))
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

/**
 * @param {ArrayBuffer|ArrayBufferView} value
 * @returns {string}
 */
function bytesToBase64(value) {
  const bytes =
    value instanceof Uint8Array
      ? value
      : ArrayBuffer.isView(value)
        ? new Uint8Array(value.buffer, value.byteOffset, value.byteLength)
        : new Uint8Array(value)
  let binary = ''
  const chunk = 0x8000
  for (let index = 0; index < bytes.length; index += chunk) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunk))
  }
  return btoa(binary)
}

/**
 * @param {string} base64
 * @param {string} type
 * @returns {Blob}
 */
function base64ToBlob(base64, type) {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index)
  return new Blob([bytes], { type })
}

/**
 * Encode the two shapes Stage 9/10 store in `blobs.data`: a Blob (tests and
 * older rows) or an ArrayBuffer (queued uploads written before the backup
 * fix). Returning `null` means the backup cannot preserve those bytes, and the
 * import below rejects it rather than restoring a corrupt upload.
 *
 * @param {any} value
 * @returns {Promise<{base64: string, type: string}|null>}
 */
async function encodeBlobData(value) {
  if (typeof Blob !== 'undefined' && value instanceof Blob) {
    if (typeof FileReader !== 'undefined') {
      return { base64: await blobToBase64(value), type: value.type || 'application/octet-stream' }
    }
    if (typeof value.arrayBuffer === 'function') {
      return {
        base64: bytesToBase64(await value.arrayBuffer()),
        type: value.type || 'application/octet-stream',
      }
    }
    return null
  }
  if (value instanceof ArrayBuffer) {
    return { base64: bytesToBase64(value), type: 'application/octet-stream' }
  }
  if (ArrayBuffer.isView(value)) {
    return { base64: bytesToBase64(value), type: 'application/octet-stream' }
  }
  if (value && typeof value.arrayBuffer === 'function') {
    return {
      base64: bytesToBase64(await value.arrayBuffer()),
      type: value.type || 'application/octet-stream',
    }
  }
  return null
}

/**
 * @returns {Promise<any>}
 */
export async function exportBackup() {
  /** @type {Record<string, any[]>} */
  const tables = {}
  for (const name of TABLES) {
    tables[name] = await db.table(name).toArray()
  }
  const blobs = []
  for (const row of await db.blobs.toArray()) {
    const encoded = await encodeBlobData(row.data)
    blobs.push(
      encoded
        ? {
            ...row,
            data: null,
            data_base64: encoded.base64,
            data_type: encoded.type,
          }
        : { ...row, data: null },
    )
  }
  const user = await getMetadata('session_user', null)
  return {
    version: BACKUP_VERSION,
    exported_at: nowIso(),
    owner: user?.id || null,
    tables,
    blobs,
  }
}

/**
 * @param {any} backup
 * @returns {Promise<void>}
 */
export async function importBackup(backup) {
  if (!backup || Number(backup.version) !== BACKUP_VERSION) {
    throw new Error('Unsupported backup version')
  }
  const currentSession = await db.metadata.get('session_user')
  const currentCachedAt = await db.metadata.get('session_user_cached_at')
  const currentOwner = currentSession?.value?.id || null
  // Backups created before owner scoping (no `owner` key) remain importable,
  // but a scoped backup can never be restored into a different account.
  if (backup.owner !== undefined && (backup.owner || null) !== currentOwner) {
    throw new Error('This backup belongs to a different account')
  }
  const tables = backup.tables || {}
  await db.transaction('rw', db.tables, async () => {
    for (const name of TABLES) {
      await db.table(name).clear()
      if (name === 'syncState') {
        // A cursor from the exporting device is meaningless here. Starting at
        // zero makes the next sync replay the feed instead of skipping it.
        continue
      }
      let rows = tables[name]
      if (name === 'metadata' && Array.isArray(rows)) {
        // A backup must never authenticate the restoring browser as the user
        // who exported it, and must not replace the live session either.
        rows = rows.filter((row) => !SESSION_METADATA_KEYS.has(row?.key))
      }
      if (Array.isArray(rows) && rows.length) await db.table(name).bulkPut(rows)
    }
    // Keep the current session so a restore while logged in survives the
    // reload that follows it.
    if (currentSession && currentSession.value) await db.metadata.put(currentSession)
    if (currentCachedAt && currentCachedAt.value) await db.metadata.put(currentCachedAt)
    await db.blobs.clear()
    for (const row of backup.blobs || []) {
      const data = row.data_base64
        ? base64ToBlob(String(row.data_base64), String(row.data_type || 'application/octet-stream'))
        : row.data
      if (data == null) {
        // Never restore a queued upload with `data: null`; the sync engine
        // would upload an empty/corrupt file.
        throw new Error(`Backup blob ${row.id || 'unknown'} has no data`)
      }
      await db.blobs.put({ ...row, data, data_base64: undefined })
    }
  })
}

/**
 * @returns {Promise<string>}
 */
export async function exportBackupJson() {
  return JSON.stringify(await exportBackup(), null, 2)
}

/**
 * @param {string} json
 * @returns {Promise<void>}
 */
export async function importBackupJson(json) {
  await importBackup(JSON.parse(json))
}
