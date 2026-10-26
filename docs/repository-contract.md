# Frontend repository contract

Status: frozen for M1/M2
Related: ADR 0001, ADR 0002, `docs/api.md`

The SPA talks to data through exactly one interface:

```
component → hook → repository → (M1) api.js → fetch
                              → (M2) Dexie + outbox → sync.js → fetch
```

Components and hooks import **only** `services/repository/index.js`. They must
never import `services/api.js`, `services/db.js`, `services/outbox.js` or
`services/sync.js`. `scripts/check_architecture.py` (Stage 8A) enforces this.

The online and local implementations must satisfy this document. A shared
contract test (`frontend/src/services/repository/contract.test.js`) runs the
same suite against both implementations; a method that only works online is
still part of the contract and must declare its offline behavior.

## 1. Universal rules

### 1.1 Entity envelope

Every synchronizable record returned by the repository has:

```js
{
  id: string,                 // non-empty; never assume UUID
  updated_at: string,         // ISO 8601 UTC with Z
  version: number,            // integer >= 0
  deleted_at: string | null,  // tombstone marker
  ...entityFields
}
```

Client-only fields may be added but must not change the canonical fields:

```js
{ pending: boolean }          // true while an outbox row is unacknowledged
```

### 1.2 Return shapes

| Operation | Returns |
|---|---|
| List | `{ items, total, limit, offset }` |
| Cursor list | `{ items, next_cursor: string \| null, has_more: boolean }` |
| Get | the full entity |
| Create | the full created entity (201 semantics) |
| Update | the full updated entity, with incremented `version` |
| Delete | `undefined` (204 semantics); local delete returns the tombstone |
| Mutation that creates a link | `{ receipt, expense, split }` as documented |

`total` is the unpaginated count after filters. `limit` echoes the applied
limit. `offset` echoes the applied offset.

### 1.3 Errors

All rejections are `RepositoryError`:

```js
class RepositoryError extends Error {
  code: string        // see below
  status: number|null // HTTP status when known
  detail: string
  fields?: object     // 422 validation map when available
  retryable: boolean
}
```

| Code | Meaning | UI behavior |
|---|---|---|
| `not_found` | 404 | show empty/not-found state |
| `validation` | 422 or local zod failure | field errors |
| `conflict` | 409 / stale `base_version` | conflict dialog |
| `unauthorized` | 401 after refresh retry | open login |
| `forbidden` | 403 (tier) | approval/tier message |
| `rate_limited` | 429 | retry with backoff |
| `network` | fetch/offline failure | offline banner, outbox retained |
| `offline_unsupported` | online-only operation attempted offline | explanatory toast |
| `server` | 5xx | retry/manual retry |
| `aborted` | caller aborted | ignore silently |

`AbortError` from `AbortSignal` is normalized to `code: 'aborted'`; hooks must
ignore it and not show an error.

### 1.4 Cancellation

Every read method accepts an optional `{ signal }` (an `AbortSignal`) as the
last argument or in its options object. Cancellation must stop the fetch or
Dexie query promptly. Mutations accept a signal too; an aborted mutation may or
may not have been applied server-side, so the outbox remains authoritative for
retry.

### 1.5 Ordering and pagination

- Expenses: `expense_date DESC, created_at DESC, id ASC` (stable tie-break).
- Activities: `time DESC, id DESC`; cursor is opaque.
- Groups: name `ASC`, then `created_at DESC`, then `id ASC` unless a
  recent/starred/archived filter supplies its own order.
- Categories: `id ASC`.
- Receipt items: `position ASC, id ASC`.
- Page size defaults to 50; maximum 200. This is enforced by the server and
  mirrored locally.

### 1.6 IDs and idempotency

- `create` accepts an optional client-generated `id`. If omitted, the server
  generates one. Offline creation always supplies an id.
- Replaying the same create (same id) is idempotent and returns the existing
  entity.
- Updates require `base_version` when called from the sync/outbox path; the
  UI-facing repository may read the current version from its local store.

## 2. Auth and session

```js
auth.me({ signal })                       // → User | null
auth.refresh({ signal })                  // → { access_token, user } | null
auth.logout({ signal })                   // → void
auth.startOAuth(provider, returnTo)       // → void (browser redirect)
auth.providers()                          // → { google, github }, cached discovery
```

`me` never throws `unauthorized`; it returns `null`. `refresh` returns `null`
when there is no valid refresh cookie. Offline, `refresh` rejects with `network`
and the session stays in its cached state.

## 3. Groups and membership

```js
groups.list({ ids?, status?, limit?, offset?, signal })
  // → { items: Group[], total, limit, offset }
groups.get(groupId, { signal })           // → Group | null
groups.details(groupId, { signal })       // → { group, participants_with_expenses }
groups.create(input, { signal })          // → Group
groups.update(groupId, input, { signal }) // → Group
groups.removeMembership(groupId, { signal }) // → void
groups.recordAccess(groupId, { signal })  // → void (debounced by caller)
groups.setStarred(groupId, value, { signal })   // → Membership
groups.setArchived(groupId, value, { signal })  // → Membership
groups.sync({ groupIds, starredGroupIds?, archivedGroupIds?, signal })
  // → { groups, user_groups, is_authenticated }
  //   sends { group_ids, starred_group_ids, archived_group_ids }
```

`status` is `'recent' | 'starred' | 'archived' | 'all'`; the local repository
resolves recent/starred/archived from Dexie metadata and the membership table.
The default and `'all'` both include archived groups, matching the server.
`ids` filters the result to exactly those groups. Guests keep star/archive in
Dexie metadata; authenticated users keep it in the membership table.
`groups.create` requires an authenticated tier on the server; offline creation
is allowed only when a cached permitted tier exists and is revalidated on push.

### Group shape

```js
{
  id, name, information, currency, currency_code, created_at,
  updated_at, version, deleted_at,
  participants: Participant[],
  user_group?: { is_starred, is_archived, created_at } | null
}
```

## 4. Participants

Participants are created and renamed through `groups.update` (the reference
form submits the whole participant set). The repository also exposes explicit
helpers for forms and sync:

```js
participants.list(groupId, { signal })          // → Participant[]
participants.upsert(groupId, input, { signal }) // → Participant
participants.remove(groupId, id, { signal })    // → void
```

`Participant` is `{ id, name, group_id, updated_at, version, deleted_at }`.

## 5. Categories

```js
categories.list({ signal })   // → Category[]
```

`Category` is `{ id: number, grouping, name }`. Categories are server-seeded
and cached locally; the local repository returns the cached 44 defaults.

## 6. Expenses

```js
expenses.list(groupId, { limit, offset, from, to, signal })
  // → { items, total, limit, offset }
expenses.get(groupId, expenseId, { signal })       // → Expense | null
expenses.create(groupId, input, { signal })        // → Expense
expenses.update(groupId, expenseId, input, { base_version?, signal }) // → Expense
expenses.remove(groupId, expenseId, { base_version?, signal })        // → void
```

Filters: `from`/`to` are inclusive `YYYY-MM-DD` dates. The list includes paid-for
rows, documents and the receipt summary needed by the row UI.

### Expense shape

```js
{
  id, group_id, expense_date: 'YYYY-MM-DD',
  title, category_id, amount, original_amount, original_currency,
  conversion_rate: string | null,
  paid_by_id, is_reimbursement, split_mode: 'EVENLY'|'BY_SHARES'|'BY_PERCENTAGE'|'BY_AMOUNT',
  notes, recurrence_rule: 'NONE'|'DAILY'|'WEEKLY'|'MONTHLY',
  is_recurring_head: boolean,
  created_at, updated_at, version, deleted_at,
  paid_for: [{ participant_id, shares }],
  documents: [{ id, url, width, height }],
  receipt: { id, status } | null
}
```

Create/update input is validated by zod and by the server. `amount` is integer
minor units; `conversion_rate` is a decimal string.

## 7. Balances

```js
balances.list(groupId, { signal })
  // → { balances: [{ participant_id, total }], reimbursements: [{ from, to, amount }] }
balances.forUser(entries, { signal })
  // entries: [{ group_id, participant_id }]
  // → [{ group_id, group_name, currency, currency_code, participant_id,
  //       participant_name, amount }]
```

Totals use the same sign convention as the reference: positive means the
participant is owed money. Computation is server-side online and mirrored in
`frontend/src/utils/` offline; both consume the shared golden fixtures.

## 8. Statistics

```js
stats.overview(groupId, { participant_id, from, to, signal })
stats.categoryExpenses(groupId, categoryId, { from, to, signal })
stats.monthExpenses(groupId, month, { from, to, signal })
```

`overview` returns totals, personal totals, spending over time, by participant,
by category, recurring summary and the range used. Drill-downs return
`{ expenses: [{ id, title, amount, expense_date }] }`.

## 9. Activities

```js
activities.list(groupId, { cursor, limit, signal })
  // → { items, next_cursor, has_more }
```

## 10. Receipts and AI

```js
receipts.get(groupId, { receipt_id?, expense_id?, signal })
  // → { receipt, items, opt_outs, split } | null
receipts.upload(groupId, file, { width, height, signal })   // → { url, width, height }
receipts.extractTotal(groupId, { image_url }, { signal })   // → Receipt
receipts.extractItems(groupId, { image_url, image_width, image_height }, { signal }) // → Receipt
receipts.addItem(groupId, receiptId, input, { signal })     // → ReceiptState
receipts.updateItem(groupId, receiptId, itemId, input, { signal }) // → ReceiptState
receipts.deleteItem(groupId, receiptId, itemId, { signal }) // → ReceiptState
receipts.setPortions(groupId, receiptId, itemId, portions, { signal }) // → ReceiptState
receipts.setOptOut(groupId, receiptId, participantId, value, { signal }) // → ReceiptState
receipts.apply(groupId, receiptId, input, { signal })       // → { receipt, expense, split }
receipts.link(groupId, receiptId, expenseId, { signal })    // → Receipt
categories.infer(title, { signal })                         // → { category_id }
```

`ReceiptState` is `{ receipt, items, opt_outs, split }`, where `split` is the
server-recomputed provisional split. Clients never send their own totals.
AI methods are **online-only**: offline they reject with
`offline_unsupported` (or queue an upload in the upload-specific flow).
`receipts.apply`/`receipts.link` are also online-only in Stage 9.

## 11. Documents

```js
documents.upload(groupId, expenseId, file, { signal }) // → Document
documents.remove(groupId, expenseId, documentId, { signal }) // → void
```

Document upload and removal are **online-only** until Stage 10B. Offline they
reject with `offline_unsupported`; the local repository never deletes a cached
document while offline.

## 12. Exports

```js
exports.csv(groupId, { from, to, signal })   // → { filename, content }
exports.json(groupId, { from, to, signal })  // → { filename, content }
```

Exports work offline from local data using the same formatting rules; the
server returns byte-identical content for the same data.

## 13. Synchronization boundary

The repository exposes one synchronization entry point, `groups.sync` (see
§3). It sends `{ group_ids, starred_group_ids, archived_group_ids }` and
returns `{ groups, user_groups, is_authenticated }`.

Runtime sync status, manual sync triggers and the conflict queue belong to the
offline sync engine behind the local repository; they are not methods on the
repository contract. Components observe pending work through the entity
`pending` flag and offline behavior through `RepositoryError` codes. The
`services/repository/index.js` module exposes a small `sync` facade
(`sync.conflicts`, `sync.resolveConflict`, `sync.backup`, `sync.restore`) plus
`subscribeSyncStatus` for the status UI; hooks import it from the repository
entry point, never from `services/sync.js`.

## 14. Runtime features and administration

```js
features.get({ signal })                     // → FeatureFlags
admin.metrics({ signal })                    // → AdminMetrics
admin.users.list({ q, tier, limit, offset, signal }) // → AdminUserList
admin.users.preauthorize({ email, tier, name }, { signal }) // → { user, is_new }
admin.users.setTier(userId, tier, { signal }) // → { id, tier }
admin.users.remove(userId, { signal })        // → void
admin.groups.list({ q, limit, offset, signal }) // → AdminGroupList
admin.groups.remove(groupId, { signal })      // → void
```

`features` is a public read. Admin methods are **online-only** and reject with
`offline_unsupported` in the local implementation. Tier changes take effect on
the next request because the server reloads the user row.

## 15. Offline capability declaration

| Method group | Offline |
|---|---|
| Groups/participants read | yes |
| Groups create/update/remove membership | yes (queued) |
| Expenses read/write | yes (queued) |
| Balances/statistics/activities/categories | yes, from local data |
| Star/archive/access | yes (queued, LWW); access recording is best-effort and skipped offline |
| Receipt item/portion/opt-out edits on cached receipts | yes (queued) |
| Receipt apply/link | no (online-only) |
| Receipt total/item extraction, category inference | no (online-only) |
| Documents upload/remove | no (online-only until Stage 10B) |
| Admin | no (online-only) |
| Auth refresh | deferred, retried on reconnect |
| Exports | yes, from local data, byte-identical to the server |

## 16. Contract tests

`contract.test.js` must assert, for both `online.js` and `local.js`:

1. every method exists with the documented arity/shape;
2. list envelopes contain `items/total/limit/offset` (or cursor fields);
3. ordering and pagination are stable;
4. an aborted read rejects with `code: 'aborted'`;
5. error mapping produces the documented `RepositoryError.code`;
6. mutations return full canonical entities with `version` and `updated_at`;
7. online-only methods reject with `offline_unsupported` in the local
   implementation when offline;
8. no method leaks a raw `Response` or `fetch` error object.
