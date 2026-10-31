# Stage 9 review — offline repository, outbox, sync, local math

**Scope:** uncommitted working tree vs `HEAD` `c642243` (57 changed/added files, ~8.6k insertions), covering `MIGRATION_PLAN.md` Stage 9A/9B/9C. Read-only review; no application code changed.
**Verdict: NEEDS REWORK.** The foundation is real (Dexie schema, transactional outbox, cursor recovery, fixture parity), but there are two blockers in the core read/restore paths and several frozen-contract/documentation gaps. Stage 9 is not shippable as claimed.

## Commands actually run

| Command | Result |
|---|---|
| `git check-ignore -v review-reports/` | `.gitignore:46:/review-reports/` |
| `cd frontend && npm test -- --run` | **32 files / 102 tests passed** |
| `cd frontend && npm run lint` | 0 warnings, 0 errors |
| `cd frontend && npm run typecheck` | clean |
| `cd frontend && npm run build` | built successfully (`index-*.js` 246.17 kB, gzip 77.84 kB) |
| `python3 scripts/check_architecture.py` | `OK: architecture boundaries, repository files, locales and e2e specs are consistent.` |
| `cd backend && PYTHONPATH=. .venv/bin/pytest -q tests/test_receipts.py` | **34 passed** |
| `cd backend && PYTHONPATH=. .venv/bin/pytest -q` | **315 passed, 2 skipped** (matches report) |
| Playwright `offline-sync.spec.ts` | **not verified** — no dev server on 5173 in this review; report's 49/49 is a prior claim |
| `python scripts/check_parity_matrix.py` | **not run**; report says it cannot run because `spliit/` is empty |

## Critical

### C1. A group-list cache row is treated as a fully bootstrapped group, so expenses/balances/stats can be permanently empty
`cacheSyncResult` writes only the group row and participants (`frontend/src/services/repository/local.js:157-198`). `ensureGroup` then returns **any** cached group without bootstrapping (`local.js:241-260`). Consequently `groups.get/details`, `expenses.list`, `balances.list`, `stats.overview` and `receipts.get` never call `bootstrapGroup` for a group that first arrived through `groups.sync`.

The only backfill is fire-and-forget prefetch of the **requested/recent** ids, capped at five, and it never dispatches a refresh:
- `local.js:967-979` calls `void prefetchGroups(requested)`;
- `frontend/src/services/sync.js:446-457` returns immediately when `requested` is empty and slices to 5;
- `useGroups` passes only `getRecentGroups()` (`frontend/src/hooks/useGroups.js:51-64`).

Concrete failures:
- First login on a device (no `recentGroups`) → `requested=[]` → nothing is prefetched. Clicking any server group shows zero expenses/balances/stats; `pull` will not repair REST-created rows because REST mutations do not append sync changes (`docs/offline-capabilities.md:46-60`).
- Returning user with >5 groups → groups 6+ are empty until a cursor-expiry bootstrap.
- Even for prefetched groups, the open page is not refreshed when prefetch finishes; the user sees empty data until the next 60s sync/broadcast.

This directly fails Stage 9A "every screen reads from IndexedDB" and "lazily bootstraps full group data" (`MIGRATION_PLAN.md:1146-1160`). The e2e test only covers a group whose expense was created locally before reload (`frontend/e2e/offline-sync.spec.ts:41-60`), so it does not catch this path.

**Fix:** mark list rows (`list_only`/`cached_at`), have `ensureGroup` bootstrap when full data is absent, preserve the marker in `cacheSyncResult`, prefetch all returned groups (not just 5 recent), and dispatch `pysplit:refresh` after prefetch.

### C2. Restoring a backup while logged in wipes the restored data on reload
`importBackup` clears every table and deliberately removes `session_user`/`session_user_cached_at` (`frontend/src/services/backup.js:99-122`). `BackupControls` immediately reloads (`frontend/src/components/system/BackupControls.jsx:32-36`). On boot, `cacheUser` compares the now-absent previous user with the current user and calls `clearAllData` (`frontend/src/services/repository/local.js:92-113`). Result: for any authenticated user, restore loads the backup, reloads, and deletes everything it just restored.

The unit test encodes the failure rather than catching it: it asserts `session_user` is absent (`frontend/src/services/offline-storage.test.js:89-101`) and never simulates a reload/auth refresh. The same restore also imports another account's `syncState` cursor and outbox (`backup.js:17-33`), with no owner field, so a backup from account A can inject A's cached groups/cursor into account B (or a guest) before the next `cacheUser` clears them.

**Fix:** preserve the *current* `session_user` while filtering the backup's; add an owner/account id and reject mismatched restores; reset or validate the cursor on restore; add a logged-in restore test (unit and/or e2e).

## High

### H1. Offline recurring statistics diverge from the server
`stats.overview` computes recurring stats from the **date-filtered list of all expenses** (`frontend/src/services/repository/local.js:1446-1459`). The server computes them from `active_recurring_expenses`: only current recurring head frames with `next_expense_created_at IS NULL`, regardless of the requested date range (`backend/app/services/stats.py:126-148`, `backend/app/services/expenses.py:989-1006`).

After sync, Dexie contains every materialized recurrence frame. Local `recurring.count`, `monthly_amount` and `yearly_amount` therefore multiply by the number of frames and change when a stats date range is selected. The parity fixture calls `getRecurringSpending` directly on a small hand-built list (`frontend/src/utils/domain/parity.test.js:76-86`), so it never exercises `stats.overview` or frames. This fails the Stage 9C "offline balances and statistics match the server after synchronization" gate.

**Fix:** persist/derive an active-head marker (or the recurring link) locally and feed only active heads to `getRecurringSpending`; do not apply the date range to recurring; add a fixture with materialized frames and a non-default range.

### H2. Pending lifecycle for groups/participants is broken and leaks permanent `pending` flags
Three related defects:

1. `groups.update` bulk-puts **every** participant with `pending: true` (`local.js:882-890`), even participants whose names did not change and for which no outbox row exists. `cacheSyncResult` then preserves all pending participants and re-puts them over the server list (`local.js:178-197`). A simple group rename leaves every participant permanently pending and can resurrect stale local names.
2. Offline group creation marks participants pending (`local.js:718-727`). On push, the server returns a **flat** group snapshot; `handleResult` calls `storeGroupSnapshot(result.entity)` (`sync.js:128-140`), but `storeGroupSnapshot` expects `{ group, participants }` and returns immediately (`sync.js:97-121`). `applyPushEntity` clears only the group (`db.js:558-576`), so the participants stay pending forever.
3. `cacheSyncResult` always writes the group with `pending: false` (`local.js:167-176`), overwriting a pending group update while its outbox row still exists.

**Fix:** only mark participants whose fields changed; clear participants after a group create; make `storeGroupSnapshot` accept the real push shape or delete it; preserve pending group fields in `cacheSyncResult`; tombstone removed participants instead of hard-deleting them (`local.js:882-883`).

### H3. Leaving a group / being removed from a group does not remove local access
`groups.removeMembership` deletes the membership row and the recent-list entry but **not the group or its data** (`local.js:899-927`). `cachedGroups` unions every primary key in `db.groups` with recent ids (`local.js:306-338`), and `cacheSyncResult` only upserts groups, never pruning ones absent from the server response (`local.js:166-212`). `ensureGroup` then returns the cached group (`local.js:241-260`).

Failure modes:
- After "leave group", the group and all cached expenses remain readable by direct URL, and `groups.list` still returns it.
- A group deleted/removed on another device stays cached; `deleteLocalGroup` is only called on a 404 bootstrap, not on a successful authenticated sync.
- Deleted groups can reappear as `cached_placeholder` entries from `recentGroups` because placeholders are added for every recent id not in the live set (`local.js:315-337`).

**Fix:** on authenticated remove/sync, delete local group data or mark the membership absent and filter `cachedGroups`/`ensureGroup` by membership; clear starred/archived metadata; prune groups absent from `/groups/sync`; delete conflicts/blobs in `deleteLocalGroup` (`db.js:587-642`).

## Medium

### M1. Offline CSV/JSON exports are not the server format (contract says byte-identical)
`exportExpenses` returns a flat array of `{date,title,category,amount,currency,paid_by,paid_for,...}` with filename `spliit-${groupId}.json/csv` (`local.js:1966-2013`). The server returns a group object with `expenses`, `participants`, `activities`, full expense fields, category objects, ascending date order, and a group/date-based filename (`backend/app/services/exports.py:56-165`). `docs/repository-contract.md:293-294` promises byte-identical content.

The online path silently falls back to this different file on any server error (`local.js:1928-1957`), so an offline or transiently failing user gets a file that cannot be re-imported/compared. **Fix:** implement the server formatter locally or return `offline_unsupported`; add a golden test comparing both.

### M2. Failure recovery leaves local state inconsistent
- `discardFailed` deletes outbox rows only (`frontend/src/services/outbox.js:145-149`; `sync.js:794-798`). A failed create leaves a ghost expense/participant/group with `pending: true` and no row that will ever sync it; a failed update leaves an unsynced local value forever.
- Receipt item DELETE is not idempotent. `pushRestOperation` sends a plain DELETE (`sync.js:193-195`); the server calls `_require_item` and 404s after the first success (`backend/app/services/receipts.py:540-544,691-709`). If the response is lost, the retry is classified non-retryable and permanently fails while the local tombstone stays pending. The lost-push e2e test covers only expense create (`e2e/offline-sync.spec.ts:217-255`), not receipt deletes.

**Fix:** on discard, revert/delete the local entity or refetch from the server; make receipt delete idempotent (204 for missing/deleted) or treat 404 after a delete as success; add lost-response tests for both.

### M3. `groups.list` does not satisfy the frozen contract
- Local returns a bare array (`local.js:664`), while online returns the server `GroupList` object (`frontend/src/services/repository/online.js:108-117`, `backend/app/schemas/groups.py:134-138`).
- `options.ids` is passed to `cachedGroups` but only **added** to a union (`local.js:306-338`), so `groups.list({ids:['g1']})` returns every cached group.
- `status:'all'` excludes archived groups (`local.js:356`), while the server's default/all path includes them (`backend/app/services/groups.py:270-297`).
- Guest starred/archived state lives only in metadata (`local.js:1004-1019`) but `composeCachedGroup`/`filterGroupStatus` read only membership (`local.js:290-299,345-362`), so guest `starred`/`archived` lists are always empty.
- Offline `groups.sync` returns all cached groups, not the requested ids (`local.js:958-965`).

No local test covers any of this; `contract.test.js` runs only against `onlineRepository` (`frontend/src/services/repository/contract.test.js:33-44`). **Fix:** return `{items,total,limit,offset}`, filter ids/status, include archived for `all`, use metadata for guests, and add a shared contract suite.

### M4. Several documented offline capabilities are not implemented
`docs/repository-contract.md:330-342` declares receipt apply/link, documents upload, and group access as queued offline. The local implementation instead:
- throws `offline_unsupported` for `receipts.apply`/`link` (`local.js:1714-1736`);
- throws for `documents.upload` (`local.js:1902-1908`) with the misleading message "queued for later";
- silently deletes the local document when offline in `documents.remove` (`local.js:1918-1924`), so the server copy resurrects on bootstrap;
- silently no-ops `groups.recordAccess` offline (`local.js:929-935`).

`docs/offline-capabilities.md:30-40,107-109,139-140` goes further, claiming blob-queued document upload, merge-queued login, `navigator.storage.persist()`/quota UI, and pending badges on participants/receipts/uploads. None exist (only the expense badge exists, `frontend/src/components/expenses/ExpenseCard.jsx:78-83`). **Fix:** implement the queues or mark these online-only and correct both docs and the Stage 9 gate table.

### M5. AbortSignal/cancellation is only partially honored
`docs/repository-contract.md:116-120` requires every read/mutation to accept a signal and stop promptly. Local methods generally check `signal.aborted` once and then run Dexie/API work to completion:
- `groups.sync` ignores its `_options` entirely (`local.js:952-996`), so `groups.list`'s `read` signal is not forwarded (`local.js:658`).
- `groups.create/update/removeMembership/setStarred/setArchived` ignore `_options` (`local.js:706,785,899,937`).
- `expenses.create/update/remove` accept options but never check the signal (`local.js:1224,1290,1360`).
- `balances.forUser` and `stats.categoryExpenses/monthExpenses` ignore their `_read` (`local.js:1414,1540-1570`).
- `receipts` mutations ignore options (`local.js:1783`).

**Fix:** thread the signal into API calls and check after awaits; add abort tests for groups/expenses/stats.

### M6. `updateMembership` clears the other flag with `undefined`
`setStarred(false)` passes `is_archived: undefined` and `setArchived(false)` passes `is_starred: undefined` (`local.js:937-950`). `updateMembership` spreads the patch over defaults (`local.js:1023-1033`), so the stored membership row gets `is_archived: undefined`/`is_starred: undefined`. Un-starring can therefore un-archive a group locally (and the enqueued payload contains the same undefined), while the metadata sets do not reflect it. **Fix:** conditionally spread only defined flags.

### M7. Scalability / ordering / debounce gaps
- `pullChanges` sends **every** local group id (`sync.js:340-352`); `SyncPullRequest.group_ids` is capped at 500 (`backend/app/schemas/sync.py:64-69`). A user with >500 cached groups gets a 422 and sync stalls.
- Per-group FIFO is enforced only when selecting a batch (`outbox.js:70-98`). Within a batch, a non-retryable failure does not stop later rows: sync results are still processed (`sync.js:253-261`) and REST loops continue (`sync.js:278-304`), causing cascading failures against a missing entity.
- Stage 9B asks for a debounced sync after mutation, but `flushGroup` calls `pushPending` immediately on every online write (`local.js:564-573`); `scheduleSync` is only used offline/conflict/retry.
- `cachedGroups` performs 2-3 queries per group (`local.js:306-338`) and `balances.forUser` reads every expense per group (`local.js:1414-1436`), so the global balance/group list are N+1. `metadataRecent` is also uncapped in `cacheSyncResult` (`local.js:209-211`) despite `rememberRecent` capping at 50.

**Fix:** batch/paginate group ids, stop a group at its first failed head, debounce online mutation sync, and batch the list/balance queries.

### M8. Documentation and the Stage 9 gate table overclaim
Concrete contradictions:
- `docs/stage-9-report.md:143` claims "every screen reads Dexie"; `useGroups`/`useActiveUser`/`useExpenseForm`/`useGlobalBalance` still read localStorage (`useGroups.js:51-53`, `useActiveUser.js:11,20`, `useExpenseForm.js:48`, `useGlobalBalance.js:32`). The report admits this later (`:182-184`).
- `docs/stage-9-report.md:145` claims `local.test.js` checks "every documented method and envelopes"; it only asserts `typeof === 'function'` (`local.test.js:137-142`).
- `docs/stage-9-report.md:148` claims tombstone handling; receipts never enter the pull feed, and REST mutations do not append changes (`docs/offline-capabilities.md:46-60`). The claim at `stage-9-report.md:167-170` that another device sees receipt edits "after bootstrap **or a pull that includes a later related change**" is false: pull never includes receipt entities.
- `docs/stage-9-report.md:149` claims pending badges; only expenses have one.
- `docs/stage-9-report.md:152` cites receipt item ids for lost-response idempotency, but the e2e test is expense create and receipt delete is not idempotent.
- `docs/stage-9-report.md:157` marks localStorage migration PASS while saying "UI still reads localStorage directly"; the migrated `activeUser`/`newUser`/`defaultSplittingOptions` metadata is never read anywhere (`local-storage-migration.js:143-146`; only tests read it).
- `docs/stage-9-report.md:158` marks backup/restore PASS because session metadata is not restored — that is the cause of C2.
- `docs/stage-9-report.md:200` admits no guest-merge e2e, while `MIGRATION_PLAN.md:1178-1185` requires scenario 6.

**Fix:** mark 9A/9B/9C gates PARTIAL/FAIL where they are, move deferred capabilities to an explicit "not implemented" list, and stop claiming byte-identical exports/tombstones/badges.

### M9. Test gaps hide the failures above
- `contract.test.js` is online-only (`contract.test.js:33-44`); there is no shared local/online contract suite.
- `local.test.js` has one method-existence test plus behavior tests, but no test for list-cache bootstrap, `groups.list` shape/ids/status, membership removal, unchanged-participant pending flags, group-create participant pending, recurring stats with frames, exports, or cancellation.
- `offline-storage.test.js` has no blob round-trip and no logged-in restore/reload test (`offline-storage.test.js:57-105`).
- `sync-recovery.test.js:55-58` asserts only `db.groups.get('g1')` is truthy, not that the bootstrap snapshot (name/version/expenses) was applied.
- `local.test.js:331-339` asserts a local spy received `groupIds`, not the actual wire payload or server behavior.
- `offline-sync.spec.ts` has four tests (cached read, offline edit, conflict, lost push) and no guest login/merge scenario (`offline-sync.spec.ts:41,62,105,217`).

**Fix:** make the contract suite run against both repositories, add the missing unit/e2e cases, and make the guest-merge scenario a Stage 9B deliverable rather than a Stage 11 deferral.

## Low / Nit

- **Dead code:** `storeGroupSnapshot` is unreachable in practice (`sync.js:97-121`); `LAST_SYNC_KEY` is written but never read (`local.js:63,228`); `removeMetadata` is unused (`db.js:100-104`); `readCursor` is re-exported but unused (`local.js:2118`); `utils/domain/dates.js` is entirely unused; `repository/index.js` exports `bootstrapGroup`/`stopSync` with no consumer (`index.js:16-24`).
- **Duplicate refresh effect:** the same five-line `pysplit:refresh` listener is copied into `useGroup.js:31-35`, `useExpenses.js:35-39`, `useBalances.js:16-20`, `useStats.js:19-23`, `useActivities.js:15-19`.
- **Migration is write-only:** `activeUser`, `newUser`, `newGroupActiveUser` and `defaultSplittingOptions` are copied into Dexie but no hook/repository reads them (`local-storage-migration.js:143-146`); `useActiveUser`'s comment claiming Stage 9C migrated it is misleading (`useActiveUser.js:4-6`).
- **Nit:** duplicated JSDoc in `frontend/src/architecture.test.js:8-9`; redundant `conflicts ? 'conflict' : count ? 'idle' : 'idle'` in `sync.js:477-484`; `normalizePaidFor` is exported but only used internally (`local.js:410`).

## Stage 9 gate mapping

| Gate | Result | Evidence |
|---|---|---|
| 9A every screen reads IndexedDB without changing hooks/components | **FAIL** | `useGroups.js:51-53`, `useActiveUser.js:11,20`, `useExpenseForm.js:48`, `useGlobalBalance.js:32` still use localStorage; report admits at `stage-9-report.md:182-184` |
| 9A cached group survives reload with API unavailable | **PASS (not run)** | `offline-sync.spec.ts:41-60`; not executed here |
| 9A automated local-contract check | **FAIL** | `contract.test.js:33-44` online-only; `local.test.js:137-142` only checks function presence |
| 9A lazy full-group bootstrap + prefetch | **FAIL** | C1 (`local.js:157-260`, `sync.js:446-457`) |
| 9B durable outbox, per-group FIFO, batches of 50, backoff | **PARTIAL** | `outbox.js:70-98` selection is FIFO; within-batch failures still push later rows (`sync.js:253-304`) |
| 9B Dexie write + outbox in one transaction | **PASS** | `local.js:750-778`, `1269-1280`, `1338-1355`, `1793-1893` |
| 9B push then pull, cursor, bootstrap fallback, tombstones | **PARTIAL** | cursor recovery `sync.js:340-407`; >500 groups breaks `sync.js:352`; receipts are not in the pull feed |
| 9B `navigator.locks` + BroadcastChannel leader election | **PARTIAL** | lock single-flight `sync.js:510-535`; BroadcastChannel only refreshes; report admits "not leader election" |
| 9B pending banner, badges, failed actions, conflict dialog | **PARTIAL** | banner/dialog exist; only expense badge (`ExpenseCard.jsx:78-83`); discard bug M2 |
| 9B offline create/edit/reload/reconnect exactly once | **PARTIAL** | expense e2e only; receipt create backend idempotency only, no e2e |
| 9B divergent edits + explicit conflict resolution | **PASS/PARTIAL** | keep-mine e2e `offline-sync.spec.ts:105-215`; server/duplicate unit only |
| 9B lost push response without duplication | **PARTIAL** | expense e2e `offline-sync.spec.ts:217-255`; receipt delete non-idempotent M2 |
| 9B offline group creation checks cached permitted tier | **PASS** | `local.js:706-715`; server revalidates `sync.py:413-418` |
| 9B account switch does not expose previous user's groups | **PARTIAL** | clear works `local.js:92-113`; membership/removal stale H3; backup cross-account C2 |
| 9B new Playwright scenario includes guest group login/merge | **FAIL** | no scenario 6; `stage-9-report.md:200` defers it; plan `MIGRATION_PLAN.md:1178-1185` |
| 9C JS mirrors replay the same fixtures as Python | **PASS** | 6 tests in `frontend/src/utils/domain/parity.test.js`; 102 unit tests green |
| 9C local balances, statistics, receipt split | **PARTIAL** | balances/receipt split good; recurring stats H1 |
| 9C localStorage migration guarded by version + zod | **PARTIAL** | migration runs (`local-storage-migration.js:135-149`) but migrated active/new/splitting metadata is unread; UI still localStorage |
| 9C versioned JSON backup/restore | **FAIL/PARTIAL** | C2; no blob test; no owner scoping |
| Full online suite remains green | **NOT VERIFIED** | report's 49/49 is a prior claim; no Playwright run in this review |

## Strengths (calibrated)

- The Dexie schema is broad and the indexes cover the main entity paths (`frontend/src/services/db.js:41-65`).
- Writes really are atomic: local entity + outbox in one Dexie transaction for groups, participants, expenses, membership and receipt items (`local.js:750-778`, `1269-1280`, `1338-1355`, `1793-1893`).
- The outbox has a genuine per-group head-of-line model, attempt counts, backoff and batch cap, with focused unit tests (`outbox.js:17-98`, `outbox.test.js`).
- Cursor recovery bootstraps every group, drops server-not-found groups, and is unit-tested (`sync.js:357-379`, `sync-recovery.test.js`).
- The domain mirrors are not fake: shares/balances/totals/receipt-split/currency/recurrence replay shared fixtures generated from the Python mirrors (`parity.test.js`, `shared/fixtures/domain/*`).
- Backend receipt item create idempotency is a small, well-scoped addition with a service-level test (`backend/app/services/receipts.py:603-611`, `tests/test_receipts.py:371-392`).
- Account switch stops/awaits sync and clears Dexie plus legacy selection keys (`local.js:92-113`).
- The repository boundary and architecture checks still pass; no hooks/components import `api/db/outbox/sync` directly.

## Prioritized fix list

1. **Fix C1 first:** make list-only groups bootstrappable; preserve `cached_at`; prefetch all returned groups and refresh the UI.
2. **Fix C2:** preserve current session on restore, add backup ownership, reset/validate cursor, add logged-in restore tests.
3. **Fix H1:** compute recurring stats from active heads only, independent of the stats date range; add a frames fixture.
4. **Fix H2:** only mark changed participants; clear participants after group create; fix/remove `storeGroupSnapshot`; preserve pending group fields.
5. **Fix H3:** prune/deny local groups without membership; clear metadata; delete conflicts/blobs on group deletion.
6. **Fix M1:** implement server-compatible offline exports or reject offline export; add a golden comparison.
7. **Fix M2:** make `discardFailed` revert local state; make receipt DELETE idempotent; add lost-response tests.
8. **Fix M3:** restore the `groups.list` contract (shape, ids, status, guest flags) and add a shared local/online suite.
9. **Fix M4/M8:** implement or explicitly defer/deny documents/apply/link/recordAccess/storage/badges/merge, and correct docs/gate table.
10. **Fix M5/M7/M9:** thread AbortSignals, batch group ids, enforce per-group stop-on-failure, debounce online pushes, and fill the test gaps.

