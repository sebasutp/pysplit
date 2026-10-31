/**
 * Dexie schema contract shared by the runtime database, the PWA build
 * metadata and the migration tests.
 *
 * Keep this module free of Dexie/browser imports: `vite.config.js` reads it at
 * build time to emit `dist/pwa-build.json`, which the running app fetches
 * before activating a waiting update.
 */

export const DATABASE_SCHEMA_VERSION = 4

export const STORES_V2 = {
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

// Stage 10B adds queued uploads. The data shape is unchanged; only the blob
// indexes grow, so a v2 database opens in place without rewriting rows.
export const STORES_V3 = {
  ...STORES_V2,
  blobs: 'id, group_id, kind, entity_id',
  outbox: '++seq, op_id, group_id, status, next_attempt_at, entity_id, entity_type',
}

// v4 replaces the separate document/receipt tables with one attachment model.
// This is a destructive development migration; old local rows are discarded.
export const STORES_V4 = {
  groups: 'id, updated_at, version, deleted_at',
  participants: 'id, group_id, updated_at, version, deleted_at, position',
  expenses: 'id, group_id, expense_date, updated_at, version, deleted_at',
  paidFor: '[expense_id+participant_id], expense_id, participant_id',
  activities: 'id, group_id, time',
  attachments: 'id, group_id, expense_id, updated_at, version, deleted_at',
  attachmentItems: 'id, attachment_id, position, updated_at, version, deleted_at',
  attachmentPortions: 'id, item_id, updated_at, version, deleted_at',
  attachmentOptOuts:
    'id, attachment_id, participant_id, updated_at, version, deleted_at',
  categories: 'id',
  userGroups: 'id, user_id, group_id, [user_id+group_id], updated_at, version, deleted_at',
  outbox: '++seq, op_id, group_id, status, next_attempt_at, entity_id, entity_type',
  syncState: 'scope',
  conflicts: '++id, group_id, entity_type, entity_id, created_at',
  blobs: 'id, group_id, kind, entity_id',
  metadata: 'key',
}

/** Tables every current build must find after a Dexie upgrade. */
export const REQUIRED_TABLES = Object.freeze(Object.keys(STORES_V4).sort())

/** Index names (the part after the primary key) for each required table. */
export const REQUIRED_INDEXES = Object.freeze(
  Object.fromEntries(
    Object.entries(STORES_V4).map(([table, spec]) => [
      table,
      spec
        .split(',')
        .map((entry) => entry.trim())
        .filter(Boolean)
        .slice(1),
    ]),
  ),
)

/** Serialisable contract emitted as `dist/pwa-build.json`. */
export const DATABASE_BUILD_CONTRACT = Object.freeze({
  schemaVersion: DATABASE_SCHEMA_VERSION,
  requiredTables: REQUIRED_TABLES,
  requiredIndexes: REQUIRED_INDEXES,
})
