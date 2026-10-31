# Stage 9 report — Offline repository, outbox, synchronization and local math

Status: complete for Stages 9A/9B/9C with the partial gates listed in §4
(the guest-merge scenario and some Stage 10B UX remain deferred).

## 1. Outcome

The SPA now reads from IndexedDB through the Dexie-backed repository and writes
to IndexedDB plus a durable outbox in one transaction. Push/pull, bootstrap
fallback, conflict handling, local balance/statistics/receipt calculations,
localStorage migration and a versioned JSON backup are implemented.

Components and hooks still import only `services/repository`. The HTTP client,
Dexie, outbox and sync engine remain behind that boundary; the architecture
checker enforces this.

## 2. Files added or changed

### Offline services

- `frontend/src/services/db.js` — Dexie schema, entity assembly, bootstrap
  snapshot replacement, full-snapshot change application.
- `frontend/src/services/outbox.js` — per-group FIFO rows (a backed-off or
  failed head holds later rows), batches of 50, retry backoff, attempt counts,
  last error, pending and failed counts, retry/discard of failed rows.
- `frontend/src/services/sync.js` — push then pull, cursors per user/guest
  scope, bootstrap fallback with cursor recovery, cross-tab single-flight via
  `navigator.locks` (not leader election), BroadcastChannel refresh,
  pending/failed/conflict counters, conflict resolution (keep mine / use server
  / duplicate as new), receipt REST transport with client-generated ids.
- `frontend/src/services/sync-events.js` — sync status observable.
- `frontend/src/services/local-storage-migration.js` — one-time migration of
  the reference localStorage keys, guarded by the `migrated_from_localstorage`
  version and validated with the same zod schemas the UI uses. The UI still
  reads localStorage directly; the Dexie copy feeds the local repository.
- `frontend/src/services/backup.js` — versioned JSON export/restore including
  outbox, conflicts, preferences and pending blobs as base64.
- `frontend/src/services/repository/local.js` — full local implementation of
  the frozen repository contract.
- `frontend/src/services/repository/index.js` — selects the local repository
  and exposes the sync/conflict/backup facade.
- Account changes (logout or a different user id) stop sync, wait for the
  in-flight cycle, clear the Dexie tables and the legacy selection keys, then
  restart sync. Backups are owner-scoped and preserve the live session on
  restore.

### Local calculations

- `frontend/src/utils/domain/shares.js`
- `frontend/src/utils/domain/balances.js`
- `frontend/src/utils/domain/totals.js`
- `frontend/src/utils/domain/receipt-split.js`
- `frontend/src/utils/domain/currency.js`
- `frontend/src/utils/domain/recurrence.js`
- `frontend/src/utils/categories.js` — the 44 default categories.
- `backend/scripts/generate_domain_fixtures.py` — regenerates the shared JSON
  fixtures from the verified Python mirrors.
- `shared/fixtures/domain/{shares,balances,totals,receipt-split,recurrence,currency}.json`

### UI and hooks

- `frontend/src/components/system/SyncStatus.jsx` — offline/syncing/pending/
  failed/error/conflict banner, manual sync, retry/discard failed operations and
  conflict dialog.
- `frontend/src/components/system/BackupControls.jsx` — user-triggered export
  and restore.
- `frontend/src/hooks/useSyncStatus.js`.
- `frontend/src/hooks/{useActivities,useBalances,useExpenses,useGroup,useStats}.js`
  — reload on the sync refresh event through the shared `useSyncRefresh` hook.
- `frontend/src/components/expenses/ExpenseCard.jsx` — per-expense pending
  badge.
- `frontend/src/App.jsx`, `main.jsx`, `pages/GroupsPage.jsx` — mount status,
  start synchronization, expose backup controls.

### Tests and tooling

- `frontend/src/utils/domain/parity.test.js` — replays the shared fixtures in
  JavaScript.
- `frontend/src/services/repository/local.test.js` — contract surface, local
  reads, canonical paid_for, account isolation, group-list envelope/pruning,
  recurring heads, exports, offline receipt edits, online-only errors and
  cancellation.
- `frontend/src/services/repository/local-bootstrap.test.js` — list-only group
  bootstrap and prefetch of every returned group.
- `frontend/src/services/outbox.test.js` — per-group head-of-line FIFO, failed
  counts/retry/discard and pending-row preservation during bootstrap.
- `frontend/src/services/sync-recovery.test.js` — expired-cursor convergence,
  >500-group pull chunking, forced-push progress cap, flat group-create results
  and failed-create discard.
- `frontend/src/services/offline-storage.test.js` — migration, backup
  round-trip, owner scoping, live-session preservation, cursor reset and blob
  round-trip.
- `frontend/src/services/sync-conflicts.test.js` — keep mine (including delete),
  use server and duplicate-as-new resolution strategies.
- `frontend/e2e/offline-sync.spec.ts` — cached reload without the API, offline
  create/edit plus reload and single delivery, two-context conflict resolution,
  and lost-push-response idempotency.
- `frontend/e2e/app.ts` — waits for the unauthenticated boot before mock login
  so a StrictMode refresh cannot invalidate the newly created session.
- `scripts/check_architecture.py`, `frontend/src/architecture.test.js` —
  require `offline-sync.spec.ts` and the local repository files.
- `dev` — raises the local sync rate limit for the parallel e2e suite;
  production defaults are unchanged.
- `frontend/package.json` — exact-pinned `dexie@4.2.1` and
  `fake-indexeddb@6.2.4`.
- `docs/offline-capabilities.md`, `docs/repository-contract.md` — implementation
  status and the allowed sync facade.

## 3. Commands run and output

```text
$ cd frontend && npm test -- --run
Test Files  33 passed (33)
     Tests 116 passed (116)

$ npm run lint
Found 0 warnings and 0 errors.

$ npm run typecheck
tsc -p jsconfig.json            # no diagnostics

$ npm run build
dist/assets/index-*.js   246.17 kB │ gzip: 77.83 kB
✓ built in 183ms

$ BASE_URL=http://127.0.0.1:5173 npx playwright test --workers=4
49 passed (46.5s)

$ cd ../backend && PYTHONPATH=. .venv/bin/pytest -q
315 passed, 2 skipped, 1 warning in 28.63s

$ cd .. && python3 scripts/check_architecture.py
OK: architecture boundaries, repository files, locales and e2e specs are consistent.
```

`python scripts/check_parity_matrix.py` cannot run in this workspace because
`spliit/` is present but empty, while `docs/reference-manifest.txt` still lists
the reference tree. Stage 9 does not change reference discovery; the checker
reported the stale-manifest failure. No matrix rows were changed by this stage.

The Playwright browser libraries were supplied from the repository-local
`.cache/libs/extract` tree via `LD_LIBRARY_PATH`; no repository file depends on
it.

## 4. Gate checklist

| Gate | Status |
|---|---|
| 9A: every screen reads Dexie without changing hooks/components | PARTIAL — entity screens read Dexie; group/active-user/default-splitting preferences still read localStorage, as noted below |
| 9A: cached group survives a reload with the API unavailable | PASS — `offline-sync.spec.ts` (not re-run in the review sandbox) |
| 9A: automated local-contract check | PARTIAL — `contract.test.js` checks method existence on both repositories; local behavior tests cover list shape, bootstrap, stats, exports and cancellation |
| 9A: lazy full-group bootstrap + prefetch | PASS — list rows are marked `list_only` and every returned group is prefetched |
| 9B: offline writes durable, per-group FIFO, batches of 50, retry/backoff | PASS — head-of-line FIFO and stop-at-first-failed-head within a batch |
| 9B: writes update Dexie and enqueue in one transaction | PASS — including receipt REST mutations |
| 9B: push/pull, cursor, tombstones, bootstrap fallback, cross-tab lock | PARTIAL — cursor recovery and >500-group chunking work; receipt entities still do not appear in the pull feed |
| 9B: pending banner, badges, failed-operation actions, conflict dialog | PARTIAL — banner/dialog/retry/discard exist; only expenses have a per-entity badge |
| 9B: offline create/edit/reload/reconnect exactly once | PARTIAL — expense e2e; receipt create idempotency is backend-only |
| 9B: divergent edits and explicit conflict resolution | PASS |
| 9B: lost push response retried without duplication | PASS — expense e2e; receipt item DELETE is now idempotent on retry |
| 9B: offline group creation checks a cached permitted tier | PASS — cached user tier check; server revalidates on push |
| 9B: account switch does not expose the previous user's groups | PASS — Dexie/selection keys are cleared; local groups are pruned when membership is gone |
| 9B: new Playwright scenario includes guest group login/merge | FAIL — deferred to Stage 11 |
| 9C: JS mirrors replay the same fixtures as Python | PASS — 6 parity tests |
| 9C: local balances, statistics and receipt split | PASS — recurring stats use active heads only |
| 9C: localStorage migration guarded by a version flag and zod validation | PARTIAL — migration runs, but the UI still reads the legacy keys directly |
| 9C: versioned JSON backup and restore | PASS — live session preserved, owner mismatch rejected, cursor reset, blob round-trip tested |
| Full online suite remains green | PASS at the previous Stage 9 run (49/49); not re-run in this sandbox |

## 5. Deviations and open questions

- The Dexie table properties are dynamic, so `db.js`, `sync.js`, `outbox.js`,
  `backup.js` and `repository/local.js` start with `// @ts-nocheck`. Their
  shapes are covered by the contract tests and the e2e suite. Replacing this
  with generated Dexie typings is a possible follow-up.
- Receipt item/portion/opt-out edits are durable locally and flushed through
  the existing REST receipt endpoints (`transport: 'rest'`). They are not
  appended to `sync_changes`, so another device never observes them as
  standalone pull items. It sees them only after a bootstrap (or after some
  later sync write causes the local client to bootstrap again). The unified
  server write path remains outstanding.
- Offline document uploads and AI receipt upload queues are explicitly deferred
  to Stage 10B; the current local repository rejects them with
  `offline_unsupported`.
- An offline reload in production requires the Stage 10A service worker. The
  Stage 9 e2e test simulates a missing API while keeping the Vite app shell
  available, which matches the Stage 9A gate ("stop the API, reload").
- The in-tab refresh event is dispatched after a completed sync. Automatic
  background retries use exponential backoff; a manual "Sync now" ignores the
  backoff so a user can force an immediate retry, but a full batch that makes no
  progress stops instead of looping forever.
- `groups.list` accepts the reference status filter, but the shell continues to
  use the recent/starred/archived lists (still in localStorage) so existing URLs
  and preferences remain unchanged.
- Logout and account switches deliberately clear local data rather than scoping
  it by user. This is the simplest isolation guarantee; unsynced local writes
  for the signed-out account are discarded on logout.
- The receipt create id is a minimal backend addition (`ReceiptItemCreate.id`);
  it only makes the existing REST transport idempotent. REST mutations still do
  not append sync change rows, so receipt edits remain invisible as standalone
  pull items until the unified write path lands.

## 6. Intentionally deferred

- Workbox precache, install prompt, update flow and offline document boot —
  Stage 10A.
- Queued image uploads, document upload/removal, storage persistence/quota UI
  and participant/receipt/upload pending badges — Stage 10B. Until then those
  operations reject with `offline_unsupported`.
- Offline receipt apply/link — online-only; not queued.
- Authenticated two-device group claim/merge and star/archive cross-device
  tests — Stage 11. There is no guest-merge e2e test yet (the Stage 9B gate for
  scenario 6 is therefore FAIL, not PASS).
- Unified server-side change rows for REST mutations and receipt entities —
  later sync hardening.
