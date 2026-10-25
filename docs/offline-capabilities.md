# Offline capabilities

Status: frozen for M2
Related: ADR 0002, `docs/repository-contract.md` §13

This is the user-visible classification every screen and the final README must
use. "Offline" means after a group has been synchronized at least once and the
application shell boots from the service worker.

> **Implementation status.** The current frontend ships the online repository;
> the offline repository, outbox and PWA behavior below are the Stage 9 target.
> On the server, only `/api/sync/push` and server-side recurrence
> materialization append sync change rows. REST mutations do not. See §2.1.

## 1. Capability matrix

| Capability | Online | Offline after sync | Queued for later |
|---|---:|---:|---:|
| Read groups, participants, expenses, activities | Yes | Yes | — |
| Create/edit/delete expenses and participants | Yes | Yes | Yes |
| Create a group | Yes (tier) | Yes, from cached permitted tier | Yes, tier revalidated on push |
| Balances and suggested reimbursements | Yes | Yes, computed locally | — |
| Statistics and drill-downs | Yes | Yes, computed locally | — |
| CSV/JSON export | Yes | Yes, from local data | — |
| Star/archive and active-user preferences | Yes | Yes | Yes |
| Group access recording | Yes | Yes | Yes, debounced |
| Receipt item/portion/opt-out edits on cached receipts | Yes | Yes | Yes |
| Receipt total/item extraction (AI) | Yes | No | Upload queued; extraction after reconnect |
| Category inference (AI) | Yes | No | No |
| Expense document upload | Yes | Yes, blob queued | Yes |
| Admin operations | Yes | No | No |
| Live currency-rate lookup | Yes | Last cached rate or manual override | — |
| Authentication refresh | Yes | Deferred | Retried on reconnect |
| Login/merge local groups | Yes | Yes, merge queued | Yes |

## 2. What each class means

### 2.1 REST writes versus `/sync/push`

This is a current limitation, not a description of the target design. The
server does **not** append `SyncChange` rows for REST mutations (`POST`, `PATCH`
or `DELETE` on groups, participants or expenses). Rows enter the change log only
when a write arrives through `/api/sync/push`, or when the server materializes
recurring expense frames.

REST and `/sync/push` are therefore not interchangeable: an online client that
edits through REST does not make that edit visible to another client that only
calls `/api/sync/pull`, unless the second client bootstraps or the record is
later written through sync. The local outbox must use `/api/sync/push` for
writes it expects other devices to pull.

A unified write path — every mutation appends a change row in the same
transaction, regardless of endpoint — is a Stage 9/C follow-up and is **not
implemented**.

### 2.2 Read-only offline

Data is served from Dexie exactly as it was last synchronized. Opening a group
that was never synchronized offline shows a clear "not available offline"
state and does not fabricate data.

### 2.3 Read-write offline (queued)

The mutation is applied to Dexie and appended to the outbox in the same
transaction. The UI updates immediately and marks the record `pending`.
Pending edits survive reload and are pushed FIFO per group when online. Queued
writes are sent through `POST /api/sync/push`, not the REST mutation endpoints.

- Guest capability URLs continue to work: the offline cache is scoped to the
  groups this browser has opened, not to a user account.
- Expense updates that conflict are never auto-resolved. The conflict dialog
  offers **keep mine**, **use server**, and **duplicate as new**.
- Group metadata, participant names and star/archive use last-writer-wins.
- A delete tombstone wins over a concurrent update; the UI shows "deleted
  elsewhere".
- An offline-created group is allowed only when a cached tier permits creation;
  the server revalidates and may reject the push with `forbidden`.

### 2.4 Online-only

Admin endpoints and AI extraction require the network. Controls are disabled
offline with an explanation; manual expense entry and manual item editing on a
cached receipt remain available.

## 3. AI and uploads offline

1. The user selects a receipt image offline. The compressed blob is stored in
   Dexie and a queued upload is created.
2. The receipt shows a **scan pending** state. No provisional totals are
   invented.
3. On reconnect the blob uploads, then AI extraction runs. A failure becomes a
   visible `FAILED` receipt with a retry action, never a crash. Retries are
   capped by `RECEIPT_MAX_ATTEMPTS` (default 3); once exhausted the image must
   be uploaded again.

AI flags come from `/api/features`; a cached flag may keep a control visible
offline, but the action is disabled with "available when online".

## 4. Storage and durability

- `navigator.storage.persist()` is requested on first sync; quota is shown in
  settings.
- A low-quota warning appears before writes fail.
- Outbox, unsynced blobs and conflict rows are never evicted by app code.
- A versioned JSON backup/restore covers groups, expenses, preferences,
  conflict records and, where feasible, pending blobs.
- Workbox caches never contain `/api` responses; data freshness is Dexie's
  responsibility, not the service worker's.

## 5. Session behavior offline

- The access token is memory-only and may expire. Local reads and writes do not
  depend on it.
- Refresh is attempted on start and when the network returns. If it fails, the
  user remains locally active and the outbox drains after a successful refresh.
- Logout clears the local user scope; guest data remains unless the user
  explicitly removes it.

## 6. Synchronization UX

A single global banner reports:

- **offline** (with pending count);
- **syncing** (with progress);
- **pending N changes**;
- **error** (with retry and last error);
- **conflict** (opens the conflict dialog).

Per-entity pending badges appear on expenses, participants, receipts and
uploads. The user can trigger a manual sync at any time.

## 7. Update behavior

A new service worker waits; the UI prompts to reload. Pending outbox rows and
blobs survive the update. The app never calls `skipWaiting()` automatically,
and a Dexie schema upgrade is tested before an update is activated.

## 8. Explicit non-goals

- No offline admin.
- No offline AI extraction or category inference.
- No CRDT or real-time co-editing.
- No promise of privacy for capability URLs: anyone with the link can read and
  write the group, online or offline.
