# Stage 9 review response

Status: all blocking and high-severity findings are addressed. Several medium
items are fixed; a few are deliberately corrected as documentation/scope issues
rather than implemented in Stage 9. Pushback is called out explicitly.

## Fixed

### C1 — list-only cache rows now bootstrap
- `cacheSyncResult` marks list rows with `list_only: true` and keeps
  `cached_at` only for rows that a full bootstrap wrote.
- `ensureGroup` bootstraps when a cached row is `list_only` (and drops
  not-found/forbidden groups).
- `prefetchGroups` no longer caps at five, skips only fully cached groups, and
  dispatches `pysplit:refresh` when it changes data.
- `groups.sync` prefetches every group returned by the server, not just the
  caller's recent ids.
- Tests: `local-bootstrap.test.js` (list-row bootstrap and seven-group
  prefetch).

### C2 — restore no longer wipes restored data
- `exportBackup` writes an `owner` account id.
- `importBackup` rejects a scoped backup restored into a different account,
  filters the exporter's session metadata, re-applies the **live** session,
  and clears `syncState` so the next sync cannot skip another device's cursor.
- Tests: live-session preservation, cursor reset, cross-account rejection,
  logged-in restore + reload simulation, blob round-trip.

### H1 — recurring statistics match the server
- `ExpenseRead` now carries `is_recurring_head`, computed in
  `expenses_to_read` from the open `RecurringExpenseLink` rows.
- Local `stats.overview` computes recurring totals from active heads only and
  independent of the requested date range.
- Backend test asserts exactly one head among materialized frames; frontend
  test asserts a non-default range does not change recurring stats.

### H2 — pending lifecycle
- `groups.update` only marks changed/new participants pending and writes
  tombstones for removed participants.
- Group-create push results are flat snapshots with participants;
  `storeGroupSnapshot` now accepts that shape and clears participant pending
  flags.
- `cacheSyncResult` preserves a pending group row instead of overwriting it
  with `pending: false`.
- Tests cover unchanged participants and group-create participant clearing
  (via the flat snapshot path).

### H3 — leaving/removal removes local access
- `removeMembership` deletes the local group, participants, expenses,
  conflicts, blobs, recent/starred/archived metadata, then queues the
  membership delete.
- Authenticated list sync prunes groups absent from the complete membership
  response and deletes local data for them.
- Pull applies `user_group` tombstones by deleting the group locally.
- `cachedGroups` now uses batched reads and membership-aware guest flags.

### M1 — offline exports use the server format
- CSV: server column order/labels, currency-code label, split-mode labels,
  per-participant signed shares, Python-style minimal quoting, BOM, and
  `Spliit Export - ...` filename.
- JSON: server group envelope, compact serialization, ascending expense order,
  category objects, activities, and date-based filename.
- Test asserts the offline CSV/JSON shape.

### M2 — failed-operation recovery and receipt delete retry
- `discardFailed` deletes local entities for failed creates and refetches the
  group from the server (or clears pending markers offline).
- Backend receipt item DELETE is idempotent: a repeat returns the current
  receipt state instead of 404.
- Tests cover local discard and the repeated DELETE.

### M3 — `groups.list` contract
- Returns `{ items, total, limit, offset }`.
- `ids` filters exactly; `status: 'all'` (and the default) includes archived
  groups; guests use Dexie metadata for star/archive; offline `groups.sync`
  returns only requested ids.
- Contract test now checks method existence on **both** repositories, and
  local tests cover envelope/ids/status.

### M5 / M6 / M7
- Signals are checked in group/expense/participant/stat mutations and passed
  to `groups.sync`; abort tests remain.
- `setStarred`/`setArchived` no longer pass `undefined` flags, and
  `updateMembership` conditionally spreads only defined fields.
- Pull batches group ids in chunks of 500 without skipping changes.
- A group stops at its first failed head for REST operations and subsequent
  sync results are left pending rather than cascading.
- Online mutations use the debounced sync path (recurring creates still push
  immediately because the server materializes frames).
- `cachedGroups`/`balances.forUser` batch their Dexie reads; recent metadata is
  capped at 50.
- Removed dead code: `LAST_SYNC_KEY`, `readCursor` re-export,
  `removeMetadata`, unused sync facade exports, `utils/domain/dates.js`.

### Documentation
- `docs/stage-9-report.md` gate table is now PARTIAL/FAIL where accurate,
  including the missing guest-merge e2e.
- `docs/repository-contract.md` documents the GroupList envelope, online-only
  document operations, receipt apply/link online-only, and the corrected
  capability table.
- `docs/offline-capabilities.md` no longer claims blob-queued uploads,
  `navigator.storage.persist()`, quota UI, storage badges, or
  login/merge queues. Those are explicitly Stage 10B/11 work.

## Pushback

1. **M4 is a scope/documentation issue, not a Stage 9 regression.** The Stage 9
   report already deferred queued uploads, storage persistence/quota UI and the
   full pending-badge matrix to Stage 10B. The implementation throwing
   `offline_unsupported` is the intended Stage 9 behavior; the docs were wrong.
   We corrected the docs instead of implementing Stage 10B early.

2. **M5 cannot mean canceling a live IndexedDB transaction.** Dexie/IndexedDB
   operations are not abortable. The safe contract is: check the signal at
   entry and between awaited steps, pass it to HTTP calls, and never abort a
   half-applied local write. We added the checks and signal propagation; asking
   Dexie to stop mid-transaction would risk the atomicity the same review
   praises.

3. **M8's "every screen reads Dexie" is too broad.** Entity screens
   (groups, expenses, balances, stats, receipts) read Dexie. The existing
   localStorage preference keys (`activeUser`, splitting defaults) are still
   read by hooks; the report already said so in §5. The gate is now marked
   PARTIAL rather than pretending otherwise. Moving synchronous preference
   readers to async Dexie reads is a UI/hook change that belongs with the
   later preference migration, not this review fix.

4. **M3's "frozen contract" was internally inconsistent.** The frozen document
   said `groups.list(...) // → list of Group`, while §16 required list
   envelopes and `online.js` returned the server `GroupList`. We aligned the
   local implementation with the server/online shape and corrected the
   document; the review's premise that the array was the only contract
   violation is only half right.

5. **M7's within-batch failure cannot be made fully transactional client-side.**
   A 50-operation `/sync/push` batch is already on the wire before the first
   result is known. We stop processing later results and leave them pending,
   which prevents client-side cascades. Preventing the server from seeing the
   later operations would require sending one operation at a time and giving up
   the required batching.

6. **M1 "byte-identical" applies only to the same data set.** Pending local
   rows by definition do not exist on the server yet, so no formatter can make
   those bytes identical. The formatter now matches the server exactly for
   synchronized data.

7. **M9's guest-merge e2e remains missing, and the gate says so.** We did not
   invent a passing result. Implementing the scenario requires the guest
   claim/merge UI flow and a Playwright run; it is recorded as FAIL rather than
   deferred silently.

## Verification after the fixes

```text
cd frontend && npm test -- --run      33 files / 116 tests passed
cd frontend && npm run lint           0 warnings, 0 errors
cd frontend && npm run typecheck      clean
cd frontend && npm run build          built (index 246.17 kB, gzip 77.83 kB)
python3 scripts/check_architecture.py OK
cd backend && PYTHONPATH=. .venv/bin/pytest -q
                                      315 passed, 2 skipped
```

Playwright was not re-run in this sandbox; the report's online-suite result is
still a prior claim.
