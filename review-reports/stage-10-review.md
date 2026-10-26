# Stage 10 review — Workbox PWA, offline uploads, storage UX

**Scope:** uncommitted working tree vs `HEAD` `a1c4855` (83 files, ~10.7k insertions), covering `MIGRATION_PLAN.md` Stage 10A/10B. Read-only review; no application code changed.
**Verdict: BLOCK.** Stage 10A is in good shape, but the core Stage 10B feature — queued document/receipt uploads — fails in a real browser and partially writes rows even when it reports failure. Backup/restore also loses those bytes, and a queued line-item receipt loses its expense link on the same sync cycle. The report's “M2 shippable” gate is not supportable.

> Note: `review-reports/` is **not** actually gitignored (`.gitignore` has no entry; the Stage 9 reports are tracked in `HEAD`). `git check-ignore review-reports/stage-10-review.md` exits 1; this file is an untracked working-tree file.

## Commands actually run

| Command | Result |
|---|---|
| `cd frontend && npm test -- --run` | **39 files / 132 tests passed** (matches report) |
| `cd frontend && npm run lint` | 0 warnings, 0 errors |
| `cd frontend && npm run typecheck` | clean |
| `cd frontend && npm run build` | PWA v2.0.0, 90 precache entries / 1543.54 KiB; `dist/sw.js`, `dist/workbox-*.js` generated |
| `python3 scripts/check_architecture.py` | `OK: architecture boundaries, repository files, locales and e2e specs are consistent.` |
| `cd frontend && npm audit --audit-level=high` | `found 0 vulnerabilities` |
| `cd backend && PYTHONPATH=. .venv/bin/pytest -q` | **315 passed, 2 skipped** (matches report) |
| PWA e2e vs `vite preview` on `:4173` | **4 passed** (`pwa.spec.ts`, `pwa-offline.spec.ts`) |
| `offline-sync.spec.ts` vs a fresh dev stack (`./dev`, `:5175`) | **4 passed** (matches report) |
| Real Chromium probe of `localRepository.documents.upload` / `receipts.upload` with a `File` | **fails**: `RepositoryError: Transaction committed too early`, while blob/doc/outbox rows still appear |
| Real Chromium `exportBackup()` after a queued blob | blob row `data` is an `ArrayBuffer`; exported backup has `data: null`, no `data_base64` |
| Real Chromium `replaceGroupSnapshot()` after a local receipt link | local receipt removed; server receipt has `expense_id: null` |
| Icon script vs committed binaries | all 9 generated PNGs match byte-for-byte (sha256 compared) |
| `package-lock.json` parse (old vs new) | lockfileVersion 3 unchanged; **330 packages added, 0 version changes, 0 removals** (churn is new transitive deps + reordering) |

**Not verified:** full Playwright suite (report claims 48/1/4), Lighthouse, `npx serve -s dist` (used `vite preview`), a real service-worker *update* e2e, background sync (not implemented), `test:coverage`.

## Critical

### C1. Offline document/receipt uploads throw in a real browser and still leave partial rows

`frontend/src/services/repository/local.js:1956-1967` (receipts) and `:2355-2366` (documents) call `queueBlob()` inside a Dexie `rw` transaction. `queueBlob()` awaits `fileBytes()` at `:2270`, and `fileBytes()` awaits `file.arrayBuffer()` (`:2242-2245`). A Dexie transaction cannot span a non-Dexie asynchronous gap; in Chromium this raises `PrematureCommitError: Transaction committed too early` (or `TransactionInactiveError`).

I ran the **actual application repository code** in Chromium (real IndexedDB, not fake-indexeddb):

- `localRepository.documents.upload('g1','e1', file, …)` → `RepositoryError: Transaction committed too early…`
- `localRepository.receipts.upload('g1', file, …)` → same error
- After both failed calls, `db.documents.count()` was still 1, `db.blobs.count()` 2, `db.outbox.count()` 2.

So the UI shows an upload error while a placeholder document, its blob, and a queued upload row may already exist. The next sync will upload data the user believes failed; a retry can duplicate it. The unit test (`upload-queue.test.js`) passes only because the fake Dexie/IndexedDB does not enforce real transaction lifetime. This directly fails the 10B gate “offline image attachments queue blobs and upload after reconnect” and “no writes are lost”.

**Reproduction:** build/run the app, open an expense, set the browser offline, attach a document (or use the receipt scan button), observe the error toast; inspect IndexedDB for the orphan rows.
**Fix:** read the file bytes (or keep a `Blob`) *before* opening the transaction, then only perform Dexie writes inside it; or wrap the external await in `Dexie.waitFor()`. Do not claim the write failed unless the transaction rolled back. Add a real-browser Playwright test that queues an image offline, reloads, reconnects, and asserts exactly one upload/one outbox row/zero blobs; the current unit test cannot catch this class of bug.

## High

### H1. A queued line-item receipt loses its expense link during the same sync cycle

`applyQueuedReceiptExtraction()` writes `expense_id` locally (`frontend/src/services/sync.js:255-273`), but `pushPending()` then marks the receipt group (`sync.js:498-500`) and immediately calls `bootstrapGroup()` (`sync.js:538-542`). `replaceGroupSnapshot()` deletes every local receipt and re-inserts the server snapshot (`frontend/src/services/db.js:476-505`). The server extract-items API is never told the expense id, so the server receipt has `expense_id: null`; the local link is overwritten.

I verified this with the real `replaceGroupSnapshot()` in Chromium: the local `local-receipt://…` row was deleted and the re-inserted server receipt had `expense_id: null`. `receipts.get(group, { expense_id })` (`local.js:1922-1934`) then returns `null`, so the user sees “No receipt is linked to this expense yet” after reconnect and cannot apply the queued scan. The report’s claim that queued line-item scans “appear through `receipts.get`” (`docs/stage-10-report.md:185-190`) is only true until this bootstrap.

The unit test hides the bug: its bootstrap fixture uses `opt_outs: ['b']` (`frontend/src/services/upload-queue.test.js:227`), but the real sync snapshot returns objects (`backend/app/services/sync.py:305-316`). `db.receiptOptOuts.put('b')` throws, the transaction aborts, and the `.catch(() => {})` in `pushPending` swallows it, so the test asserts the pre-bootstrap `expense_id: 'e1'` at `:234-238` and passes.

**Fix:** include `expense_id` in the extract-items request and link server-side, or re-link/preserve the local receipt after the bootstrap. Fix the fixture to use the real snapshot shape and assert `receipts.get(expenseId)` after a successful bootstrap.

### H2. Backup/restore silently drops every queued upload’s bytes

Stage 10 stores queued upload data as an `ArrayBuffer` (`local.js:2270-2281`), but the existing backup code only base64-encodes a `Blob` or an object with `.arrayBuffer()` (`frontend/src/services/backup.js:74-88`). An `ArrayBuffer` falls into the `{ ...row, data: null }` branch.

Verified with the real repository in Chromium: one queued blob existed, and `exportBackup()` returned `blobs: [{ hasB64: false, data: null }]`. Restore then puts a blob with `data: null`; `queuedFile()` (`sync.js:242-245`) creates a `File` from `[null]`, uploading corrupt content. This contradicts `docs/offline-capabilities.md:117-120` (“pending blobs where the browser can read them”) and the report’s backup claim. The Stage 9 blob round-trip test mocks a `Blob` (`offline-storage.test.js:136-149`), so it does not exercise the Stage 10 shape.

**Fix:** store `Blob` rather than `ArrayBuffer`, or teach backup/import to handle both; add a real-shape test that exports, clears, restores, and compares bytes. Include the blob in the versioned backup format rather than a side channel that can silently null it.

### H3. Total-only queued receipt results are written to metadata nothing reads

`sync.js:396-404` stores the extraction under `pending_receipt_total:<group>`. A repository-wide grep finds no reader for that key. After reconnect the extraction is paid for and persisted, but the user sees nothing and `ReceiptsPage` never restores the amount. The report admits the auto-fill gap (`docs/stage-10-report.md:185-190`), but the gate says “no writes are lost” and “queued receipt runs extraction and shows scan pending” PASS. This is a lost user-visible result, not just a deferred polish item.

**Fix:** surface the pending totals (restore action / notification / prefill), consume and clear the metadata, and test the reconnect-to-visible-result path. Otherwise mark the feature partial rather than PASS.

### H4. The “pre-activation Dexie migration probe” cannot test the incoming build

`activateUpdate()` calls `verifyDatabaseCompatibility()` before `updateServiceWorker(true)` (`frontend/src/services/pwa.js:114-126`). But the probe is the **currently running** code (`frontend/src/services/db.js:98-106`): it opens the already-current DB and only checks table names. The waiting service worker’s new JavaScript and its new Dexie version are not loaded, so a broken future schema upgrade is only discovered after the reload; the probe does nothing to prevent it. It also does not verify indexes or data, only table names.

`db-migration.test.js` tests v2→v3, i.e. the current code, not a future update. The gate table’s “pre-activation probe” PASS and `docs/offline-capabilities.md:156-158` are therefore unsupported.

**Fix:** emit the new build’s Dexie version/required tables/indexes into the precache manifest and compare them before activating; or perform the migration with the new code in a guarded staging step with rollback. At minimum, document that this is only a current-DB sanity check, and add an update e2e with a deliberately newer schema.

## Medium

- **PWA e2e skip on a broken production build.** `frontend/e2e/pwa.spec.ts:8-26,46-47,69-70,95-96` and `pwa-offline.spec.ts:5-23,112-113` skip whenever the manifest/SW is absent. A regression that removes the manifest or breaks SW activation turns the whole PWA gate into “4 skipped”, not failures. Gate the skip on an explicit “production PWA” flag (or `BASE_URL` port), and fail when the build is supposed to be a PWA.
- **No real update e2e.** `pwa.test.js` mocks `registerSW`; `pwa-offline.spec.ts` verifies an offline reload, not an update wait/activate/Dexie survival cycle. The report’s “update flow tests” and “pending outbox survives updates” are stronger than the evidence. Add a preview build with two SW versions and assert the waiting banner + explicit reload + preserved outbox.
- **Custom runtime caches are never cleaned.** `frontend/pwa.config.js:72-76` hard-codes `pysplit-images-v1`/`pysplit-fonts-v1`; `cleanupOutdatedCaches` only removes Workbox precache entries. Changing the config to `-v2` leaves the old cache behind forever, and the report’s “versioned names and cleanup” PASS is an overclaim. Include the build version in cache names and delete old caches on activation, or document the limitation.
- **Online creates now block on the network, regressing Stage 9’s debounced path.** `local.js:904-907` and `:1450-1455` await `flushGroup(..., { immediate: true })`, and `api.js` has no request timeout. On a captive portal/blackholed network, submitting a group/expense can hang before navigating; the Stage 9 response explicitly said online mutations use the debounced sync path. Keep the local write immediate and schedule the push, or race the ack with a short timeout.
- **`discardFailed` does not clean the new blob entities.** `sync.js:1042-1071` handles expenses/participants/receipt items/opt-outs, but `document_upload`/`receipt_upload` rows are only added to `groups`; their `db.blobs` row and pending placeholder remain after the outbox row is discarded. Orphaned blobs consume quota and an offline placeholder can stay “Pending upload” forever. Delete `meta.blob_id` and the placeholder (or refetch) on discard.
- **Docs overclaim.** `docs/offline-capabilities.md:96-107` says uploads commit in “the same Dexie transaction” (false in real browsers) and that receipt-only uploads store their result (mode `null` deletes the blob and stores nothing). `docs/repository-contract.md:279-297` describes the queued flow as if it worked. `docs/stage-10-report.md:173-178` marks the broken upload paths PASS/M2 shippable; §5’s line-item claim is false after bootstrap. Correct these to PARTIAL/FAIL and list the transaction/backup/link issues.

## Low / nits

- `frontend/scripts/generate-pwa-icons.py:134,156` creates a full `icon(...)` PNG and discards it (`mark`/`del mark`) on every splash; remove the dead work. “Deterministic on any machine” is also stronger than zlib output guarantees across zlib versions (the committed files do match the script here).
- Every new `Pwa`/`Storage`/`ReceiptItems` string is English in all 35 locales (keys/placeholders are valid; translations are not). `Pwa.updateDescription` still says “Spliit” (`en-US.json:632`), inconsistent with the pysplit branding. If English fallback is intentional until translation, say so in the report.
- `pwa.config.js:98-102` sets a `cacheName` on the `NetworkOnly` route; Workbox ignores it. `/\/api\//` is path-based only, so an API base without `/api` would not be excluded.
- `pwa.js` exposes `registration`/`updateServiceWorker` state that `usePwa` drops; `useOnlineStatus` duplicates `useSyncStatus().status.online`. Minor dead surface/duplication.
- `productionPwa`/`ensureController` are duplicated in the two PWA specs; extract a helper.
- The package-lock churn is **not** a problem: no versions changed, 330 packages added, lockfile v3. The generated icons match the committed script exactly. State that in the report instead of treating the line count as evidence.

## Recommendation

1. Fix C1 first (read blob bytes before the transaction, add a real-browser offline-upload test).
2. Fix H1 (server-side expense link or post-bootstrap re-link), H2 (backup both shapes), H3 (surface/consume the pending total), and H4 (real pre-update schema check or a corrected claim).
3. Then correct the overclaimed gate table and add the missing update/no-skip e2e before calling M2 shippable.
