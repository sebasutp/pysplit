# Offline capabilities

Status: frozen for M2
Related: ADR 0002, `docs/repository-contract.md` §13

This is the user-visible classification every screen and the final README must
use. "Offline" means after a group has been synchronized at least once and the
application shell boots from the service worker.

> **Implementation status.** Stage 10 ships the Workbox service worker,
> installable manifest, explicit update prompt, storage/quota panel and durable
> queued uploads on top of the Stage 9 Dexie repository. An offline reload boots
> the complete application shell from the precache; `/api` is NetworkOnly.
> On the server, `/api/sync/push` and recurrence materialization append sync
> change rows. REST mutations still do not; the outbox therefore uses
> `/sync/push` for all synchronizable writes. Receipt item edits use a REST
> transport in the outbox and are refreshed by bootstrap rather than appearing
> in another device's change feed. Receipt image/document uploads are stored as
> blobs in Dexie and uploaded after reconnect; receipt extraction runs then.
> Receipt apply/link and category inference remain online-only. See §2.1 and §3.

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
| Group access recording | Yes | Best effort | No; skipped offline |
| Receipt item/portion/opt-out edits on cached receipts | Yes | Yes | Yes |
| Receipt total/item extraction (AI) | Yes | No | Yes; image upload queues, extraction runs after reconnect |
| Category inference (AI) | Yes | No | No |
| Expense document upload/removal | Yes | Yes, placeholder shown | Yes; blobs upload after reconnect |
| Admin operations | Yes | No | No |
| Live currency-rate lookup | Yes | Last cached rate or manual override | — |
| Authentication refresh | Yes | Deferred | Retried on reconnect |
| Login/merge local groups | Yes | Not implemented | Stage 11 |

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

- Guest capability URLs continue to work while browsing as a guest. The cache
  is not scoped per account; logout or an account switch clears it (see §5).
- Expense updates that conflict are never auto-resolved. The conflict dialog
  offers **keep mine**, **use server**, and **duplicate as new**.
- Group metadata, participant names and star/archive use last-writer-wins.
- A delete tombstone wins over a concurrent update; the UI shows "deleted
  elsewhere".
- An offline-created group is allowed only when a cached tier permits creation;
  the server revalidates and may reject the push with `forbidden`.

### 2.4 Online-only

Admin endpoints, live AI extraction and category inference require the network.
Offline the receipt upload path stores the image and shows a **scan queued**
state; extraction itself starts after reconnect. Manual expense entry and manual
item editing on a cached receipt remain available, and the UI explains why a
scan is waiting.

## 3. AI and uploads offline

Image attachments are durable offline writes. `receipts.upload` and
`documents.upload` read the file bytes **before** opening the Dexie transaction,
then store the blob and append the queued operation inside it. Reading a
`File` inside the transaction would let it expire in a real browser
(`PrematureCommitError`) and leave partial rows behind, so the transaction only
contains Dexie work. The UI immediately shows a local receipt/document
placeholder with a pending marker. When the browser reconnects the sync engine
uploads the blob, runs the requested total or line-item extraction, replaces
the placeholder with the canonical server rows and removes the local blob.
Retries keep the uploaded image URL so a lost extraction response does not
upload a second copy.

Line-item scans send the known `expense_id` with `extract-items`, so the server
stores the link before the post-sync bootstrap replaces the local receipt.
Total-only scans have no expense to link; their result is kept as pending
metadata and offered on the next new expense form ("Use scanned total"), where
applying or dismissing it consumes the entry.

The AI request itself is never attempted offline. Receipt-only uploads without
an extraction request are also flushed. AI flags still come from `/api/features`;
the UI states that scanning resumes online while manual entry and item editing
stay available.

## 4. Storage and durability

- The group list shows a storage panel with usage/quota, a low-space warning at
  75% and a critical warning at 90%. A user action calls
  `navigator.storage.persist()` and reports whether storage is persistent.
- Outbox, conflict rows and any blobs already stored by the app are never
  evicted by app code.
- A versioned JSON backup/restore covers groups, expenses, preferences,
  conflict records and pending blobs. Both storage shapes are encoded: `Blob`
  rows and the `ArrayBuffer` rows written by the upload queue. A backup whose
  blob bytes are missing is rejected rather than restored as a corrupt upload.
  Restores preserve the live session, reject a backup from another account and
  reset the sync cursor.
- Workbox caches never contain `/api` responses; data freshness is Dexie's
  responsibility, not the service worker's.

## 5. Session behavior offline

- The access token is memory-only and may expire. Local reads and writes do not
  depend on it.
- Refresh is attempted on start and when the network returns. If it fails, the
  user remains locally active and the outbox drains after a successful refresh.
- Logout and account switches stop synchronization, wait for the in-flight
  cycle, then clear all Dexie tables and the legacy selection keys. Unsynced
  local writes for the signed-out account are discarded. This prevents one
  account's cached groups from being claimed by the next account on the same
  browser.

## 6. Synchronization UX

A single global banner reports:

- **offline** (with pending count);
- **syncing** (with progress);
- **pending N changes**;
- **failed N changes** (with retry and discard);
- **error** (with retry and last error);
- **conflict** (opens the conflict dialog).

Pending markers appear on expenses, changed participants, pending receipt
scans and queued document uploads. The storage panel includes the same backup
controls as before, so a low-quota warning is actionable. The user can trigger a
manual sync at any time; startup, `online`, visibility, mutation and manual
retry are the reliable triggers. Background Sync is not required and is not
relied upon.

## 7. Update behavior

A new service worker waits; the UI prompts to reload. Pending outbox rows and
blobs survive the update. The app never calls `skipWaiting()` automatically.
Before activation the running app:

1. opens the current Dexie database and checks every required table and index;
2. fetches the waiting build's `pwa-build.json` (not precached, `no-store`)
   and rejects an update whose declared Dexie version is older or whose
   contract drops a table/index the current database uses.

The second check compares build contracts; it does not execute the incoming
build's migration. A truly broken future migration still needs a staged
migration test or an update e2e with a deliberately newer schema. When the file
cannot be fetched, activation is refused and the prompt stays visible so the
user can export a backup first.

Runtime image/font caches are versioned (`CACHE_VERSION` in `pwa.config.js`).
After the new worker takes control the app deletes older `pysplit-images-*` and
`pysplit-fonts-*` caches; `cleanupOutdatedCaches` only covers Workbox precache
entries.

## 8. Explicit non-goals

- No offline admin.
- No offline AI extraction or category inference.
- No CRDT or real-time co-editing.
- No promise of privacy for capability URLs: anyone with the link can read and
  write the group, online or offline.
