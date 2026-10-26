# Offline capabilities

Status: frozen for M2
Related: ADR 0002, `docs/repository-contract.md` §13

This is the user-visible classification every screen and the final README must
use. "Offline" means after a group has been synchronized at least once and the
application shell boots from the service worker.

> **Implementation status.** Stage 9 ships the Dexie-backed local repository,
> durable outbox, push/pull engine, conflict queue, local domain calculations,
> localStorage migration and JSON backup. Stage 10 adds the Workbox service
> worker and installable PWA; until then an offline reload requires the app
> shell to be served by the dev server or an already-installed cache. On the
> server, `/api/sync/push` and recurrence materialization append sync change
> rows. REST mutations still do not; the outbox therefore uses `/sync/push`
> for all synchronizable writes. Receipt item edits use a REST transport in the
> outbox and are refreshed by bootstrap rather than appearing in another
> device's change feed. Receipt apply/link and document upload/removal are
> online-only in Stage 9. See §2.1 and §3.

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
| Receipt total/item extraction (AI) | Yes | No | No; online-only until Stage 10B |
| Category inference (AI) | Yes | No | No |
| Expense document upload/removal | Yes | No | No; online-only until Stage 10B |
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

Admin endpoints and AI extraction require the network. Controls are disabled
offline with an explanation; manual expense entry and manual item editing on a
cached receipt remain available.

## 3. AI and uploads offline

AI extraction and document uploads are **online-only** in Stage 9. Offline the
repository rejects them with `offline_unsupported`; the UI must disable the
controls with an explanation. The queued-blob flow (scan pending, retry caps,
`RECEIPT_MAX_ATTEMPTS`, local placeholder documents) belongs to Stage 10B and is
not implemented.

AI flags come from `/api/features`; a cached flag may keep a control visible
offline, but the action is disabled with "available when online".

## 4. Storage and durability

- `navigator.storage.persist()` and the quota UI are **not implemented** in
  Stage 9; they are Stage 10B work.
- Outbox, conflict rows and any blobs already stored by the app are never
  evicted by app code.
- A versioned JSON backup/restore covers groups, expenses, preferences,
  conflict records and pending blobs where the browser can read them. Restores
  preserve the live session, reject a backup from another account and reset the
  sync cursor.
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

Per-entity pending badges are currently shown on expenses only. Participant,
receipt and upload badges are Stage 10B work. The user can trigger a manual sync
at any time.

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
