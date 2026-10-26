# Stage 10 report — Installable PWA and offline UX

Status: complete for Stages 10A and 10B, with the limitations in §5. M2 is
shippable.

## 1. Outcome

The SPA now builds a Workbox service worker and an installable manifest, boots
the complete shell offline, never caches `/api` responses, and asks before
activating an update. Pending outbox rows and queued upload blobs survive
reloads and updates.

Offline image attachments are durable. Document and receipt images are stored
as blobs in Dexie and queued in the outbox; after reconnect they upload, run the
requested AI extraction, and replace their local placeholders. File bytes are
read **before** the Dexie transaction, so a real browser cannot expire the
transaction mid-write. Line-item scans carry their `expense_id` to the server so
the post-sync bootstrap keeps the link; total-only scan results are surfaced on
the next new expense form instead of being stored unread. The UI shows pending
markers and a scan-queued state. AI calls themselves remain online-only.

### Review follow-up

The Stage 10 review (`review-reports/stage-10-review.md`) found real-browser
failures that the fake-IndexedDB unit tests could not see. This revision fixes
them:

- **C1** — uploads read bytes before opening the transaction; a real-Chromium
  offline document upload is now part of `offline-sync.spec.ts` and asserts one
  blob, one outbox row, one server document, and zero queued rows after sync.
- **H1** — `extract-items` accepts `expense_id`; the server links the receipt
  before extraction, and the upload-queue test now uses the real snapshot shape
  and checks `receipts.get(expenseId)` after bootstrap.
- **H2** — backup/export handles both `Blob` and `ArrayBuffer` blob rows, and a
  restore with missing bytes fails instead of uploading a corrupt file.
- **H3** — `receipts.pendingTotal`/`clearPendingTotal` expose the queued
  total-only extraction; the expense form offers "Use scanned total" and
  consumes it.
- **H4** — the build emits `dist/pwa-build.json` with the Dexie version, tables
  and indexes. Activation compares it before reloading. This validates the
  incoming build contract, not the migration itself; the remaining limitation is
  stated in §5 and in `docs/offline-capabilities.md` §7.
- **Medium** — PWA specs fail (rather than skip) when a production build was
  requested; custom runtime caches are versioned and cleaned; failed queued
  uploads delete their blob/placeholder; online create acknowledgement is
  bounded by a timeout; docs no longer claim the old broken behavior.

## 2. Files added or changed

### PWA and install/update

- `frontend/pwa.config.js` — manifest, icons, shortcuts, precache policy,
  versioned image/font caches, `/api` NetworkOnly, navigation fallback.
- `frontend/vite.config.js` — `vite-plugin-pwa@2.0.0` with prompt registration,
  plus the `pwa-build.json` Dexie-contract emitter.
- `frontend/src/services/db-schema.js` — shared Dexie version, store definitions,
  required tables/indexes and the serialisable build contract.
- `frontend/index.html` — manifest/theme metadata, Apple touch icon and splash
  links.
- `frontend/public/icons/*`, `frontend/public/splash/*`,
  `frontend/public/apple-touch-icon.png`, `frontend/public/favicon.png` —
  generated icons and iOS splash images.
- `frontend/scripts/generate-pwa-icons.py` and the `icons` package script —
  icon generation without extra dependencies; the committed PNGs match the
  script byte-for-byte in this environment (zlib output can differ across zlib
  versions, so "deterministic" is not a cross-machine guarantee).
- `frontend/src/services/pwa.js` — manual registration, update state, explicit
  activation after the current-DB probe and incoming-build contract check, and
  cleanup of older runtime caches.
- `frontend/src/hooks/usePwa.js` — install prompt, standalone detection,
  update/offline states and explicit reload action.
- `frontend/src/components/system/PwaUpdatePrompt.jsx` — install button,
  offline-ready notice, update banner and error display.
- `frontend/src/App.jsx`, `frontend/src/main.jsx` — mount the prompt and start
  registration.

### Offline persistence and uploads

- `frontend/src/services/db.js` — Dexie v3 (blob/outbox indexes),
  `verifyDatabaseCompatibility()`, incoming-build contract validation and the
  required table/index contract.
- `frontend/src/services/repository/local.js` — queued document upload/remove,
  queued receipt image upload plus pending receipt state, offline extraction
  mode hand-off, pending markers, pending-total accessors, read-before-transaction
  file handling, and bounded server acknowledgement for online group/expense
  creates.
- `frontend/src/services/sync.js` — blob-upload transport, upload URL reuse on
  retry, document replacement, `expense_id` hand-off for line-item extraction,
  receipt extraction application, opt-out and portion persistence, blob cleanup
  on discard, and no extra bootstrap for document uploads.
- `frontend/src/services/backup.js` — backup/restore of both `Blob` and
  `ArrayBuffer` queued bytes, with missing bytes rejected.
- `frontend/src/services/storage.js`, `frontend/src/hooks/useStorageStatus.js`,
  `frontend/src/components/system/StorageStatus.jsx` — persistence request,
  usage/quota, warning thresholds and backup controls.
- `frontend/src/components/groups/GroupForm.jsx` — participant pending marker.
- `frontend/src/components/expenses/ExpenseDocumentsCard.jsx` — queued document
  marker and non-link placeholder rendering.
- `frontend/src/components/expenses/ReceiptScanButton.jsx` and
  `frontend/src/pages/group/ReceiptItemsPage.jsx` — offline queue explanation,
  scan-pending copy and expense linkage for queued scans.
- `frontend/src/hooks/useOnlineStatus.js` — connectivity state without importing
  the sync engine.
- Locale files — `Pwa`, `Storage`, `Pending`, receipt/document queue keys in all
  35 locales.

### Tests and verification

- `frontend/src/services/pwa-config.test.js` — manifest, icons, shortcuts and
  Workbox policy.
- `frontend/src/services/pwa.test.js` — prompt registration, explicit update,
  failed Dexie probe, incompatible incoming contract, cache cleanup and
  registration errors.
- `frontend/src/hooks/usePwa.test.js` — install prompt and update state.
- `frontend/src/services/db-migration.test.js` — v2 → v3 upgrade preserves
  cached groups, metadata and pending outbox rows; incoming build contracts that
  are older or drop a table/index are rejected, and the contract fetch bypasses
  the HTTP cache.
- `frontend/src/services/offline-storage.test.js` — blob round-trip for both
  storage shapes, plus rejection of a backup with missing bytes.
- `frontend/src/services/storage.test.js` — quota thresholds, formatting,
  persistence request.
- `frontend/src/services/upload-queue.test.js` — offline document queue and
  upload, receipt scan placeholder, `expense_id` hand-off, real snapshot shape
  and post-bootstrap `receipts.get(expenseId)`.
- `frontend/src/components/expenses/ExpenseForm.test.jsx` — queued total-only
  receipt result is surfaced, applied and consumed.
- `frontend/e2e/pwa.spec.ts` — installability, cache contents/no `/api`,
  offline unknown-route fallback; fails on a promised production build instead
  of silently skipping.
- `frontend/e2e/pwa-offline.spec.ts` — cached group and pending outbox survive
  a full offline reload under the service worker.
- `frontend/e2e/pwa-helpers.ts` — shared production-PWA detection/controller
  helpers.
- `frontend/e2e/app.ts`, `frontend/e2e/offline-sync.spec.ts` — deterministic
  active-user dismissal, sync triggers and a real-Chromium offline document
  upload/reconnect scenario.
- `scripts/check_architecture.py`, `frontend/src/architecture.test.js` — require
  the two PWA specs.

### Documentation and dependencies

- `frontend/package.json` / `package-lock.json` — exact-pinned
  `vite-plugin-pwa@2.0.0`.
- `docs/offline-capabilities.md`, `docs/repository-contract.md` — queued uploads,
  scan-pending behavior, persistence/quota and update semantics.

## 3. Commands run and output

```text
$ cd frontend && npm test -- --run
Test Files  39 passed (39)
     Tests  140 passed (140)

$ npm run lint
Found 0 warnings and 0 errors.

$ npm run typecheck
tsc -p jsconfig.json            # no diagnostics

$ npm run build
PWA v2.0.0
mode      generateSW
precache  90 entries (1548.14 KiB)
files generated
  dist/sw.js
  dist/workbox-*.js
  dist/pwa-build.json

$ npx vite preview --port 4174     # 4173 was occupied in the sandbox
$ BASE_URL=http://127.0.0.1:4174 PWA_E2E=1 npx playwright test \
    e2e/pwa.spec.ts e2e/pwa-offline.spec.ts --workers=1
4 passed

$ BASE_URL=http://127.0.0.1:5173 npx playwright test \
    e2e/offline-sync.spec.ts --workers=1
5 passed (includes the real-Chromium offline document upload)

$ cd ../backend && PYTHONPATH=. .venv/bin/pytest -q
316 passed, 2 skipped

$ PYTHONPATH=. .venv-work/bin/python scripts/export_openapi.py
Wrote docs/openapi.json (54 paths)

$ npm audit --audit-level=high
found 0 vulnerabilities

$ python3 scripts/check_architecture.py
OK: architecture boundaries, repository files, locales and e2e specs are consistent.
```

`PWA_E2E=1` (also implied by a `:4173` base URL) makes the PWA specs fail when
the manifest or active worker is missing instead of skipping. The complete
Playwright suite was not rerun in this sandbox after the review fixes; the
Stage 10 paths above were. The previous full-suite run had one
environment-sensitive failure,
`global-balance.spec.ts::reports being settled up when every balance is zero`,
which passes in isolation against the shared development database. No Stage 10
PWA/offline test failed.

The PWA specs were run against `vite preview` rather than `npx serve` because
`serve` is not a project dependency. The build output, manifest and service
worker are identical.

The `package-lock.json` change is expected transitive dependency churn from
`vite-plugin-pwa`: lockfile v3 is unchanged, with no package version changes or
removals (the added packages are the plugin's transitive dependencies).

Lighthouse was not available in the sandbox image. Installability is covered by
the generated manifest and the Playwright checks for the manifest, icon files
and installation metadata.

## 4. Gate checklist

| Gate | Status |
|---|---|
| 10A: precache HTML/JS/CSS/fonts/icons/manifest | PASS — 90 precache entries |
| 10A: `navigateFallback: '/index.html'` and unknown-route fallback | PASS — `pwa.spec.ts` offline shell |
| 10A: image/font runtime caches, versioned names and cleanup | PASS — `pwa.config.js` + unit test |
| 10A: `/api` explicitly NetworkOnly and never cached | PASS — cache inspection e2e |
| 10A: manifest name/short name/start `/groups`/standalone/colors/192/512/maskable/shortcuts | PASS — manifest e2e |
| 10A: Apple touch icon and splash metadata | PASS — generated assets + HTML assertion |
| 10A: update prompt with explicit reload, no automatic skipWaiting | PASS — service/hook tests; generated SW has only the message-triggered skip |
| 10A: Dexie schema compatibility checked before activation | PASS with caveat — current DB tables/indexes plus the incoming build's emitted `pwa-build.json` contract are checked; the incoming migration itself is not executed (see §5) |
| 10A: installability, cache contents, offline boot, update flow tests | PASS for installability/cache/offline e2e and update-prompt/build-contract unit tests; no two-version service-worker update e2e (see §5). Missing manifest/worker fails on `PWA_E2E=1` or `:4173` |
| 10B: global offline/syncing/pending/error/retry banner | PASS — existing banner plus upload operations in the same pending count |
| 10B: per-entity pending markers | PASS — expenses, participants, receipt scans, document uploads |
| 10B: startup/online/visibility/mutation/manual triggers | PASS — existing sync triggers; Background Sync is optional and not relied on |
| 10B: `navigator.storage.persist()`, quota display, low-quota warning, backup | PASS — storage panel + unit tests; backup preserves both blob storage shapes |
| 10B: offline image attachments queue blobs and upload after reconnect | PASS — unit tests plus a real-Chromium offline document scenario (exactly one server document, zero blobs/outbox rows after sync) |
| 10B: queued receipt runs extraction and shows scan pending | PASS — placeholder receipt, scan-pending UI, server-side `expense_id` link for line-item scans |
| 10B: total-only queued receipt result is visible | PASS — pending-total banner on the next new expense form; apply/dismiss consumes it |
| 10B: AI offline is explained; manual entry works | PASS — queue copy; manual forms unchanged |
| 10B: queued operations survive reload | PASS — offline-sync (5/5) and PWA-offline scenarios |
| 10B: complete offline test matrix green | PASS for Stage 10 paths (offline-sync 5/5, PWA 4/4) |
| M2 shippable | PASS (with the limitations below) |

## 5. Deviations and open questions

- Background Sync is not registered. The plan makes it optional; startup,
  `online`, visibility, mutation, manual retry and the 60-second interval cover
  the required reliable paths.
- The pre-activation check cannot execute the waiting build's Dexie migration.
  It validates the current database and compares the incoming build's emitted
  version/table/index contract; a deliberately broken migration still needs a
  staged migration or a two-version update e2e. This limitation is explicit in
  `docs/offline-capabilities.md` §7.
- There is no two-version service-worker update e2e yet. The waiting-prompt,
  explicit activation, failed-probe and build-contract paths are covered by
  `pwa.test.js`/`db-migration.test.js`; the PWA e2e covers installability,
  cache contents and offline reload. A staged two-build preview is deferred
  with the deployment work.
- A queued **total-only** receipt scan has no expense to link. After reconnect
  its result is stored locally and offered on the next new expense form, where
  "Use scanned total" applies it or "Dismiss" consumes it. It is not
  automatically applied to an arbitrary expense. Queued **line-item** scans do
  replace their placeholder and keep their link through the server and the
  post-sync bootstrap.
- The PWA specs skip on the Vite dev server because PWA dev mode is disabled.
  They must run against a production build (`vite preview` or a static server),
  which is what the Stage 10 gate does; `PWA_E2E=1` makes a missing PWA build a
  failure.
- The complete Playwright suite was not rerun after the review fixes; the Stage
  10 paths were. The previous full run had one environment-sensitive
  global-balance timeout described in §3, which passes in isolation.
- Upload retries reuse the stored receipt image URL after a lost extraction
  response. Document uploads do not have a client-supplied idempotency key in
  the current backend API, so a lost document-upload response can create a
  duplicate server document; the local placeholder is still replaced by one
  canonical row. The real-browser test covers the normal queue/upload path, not
  a lost document response.
- An online group/expense create waits at most four seconds for the server
  acknowledgement. On a captive portal the local row remains pending and the
  normal sync triggers retry it; the form no longer hangs indefinitely.
- Every locale has the new `Pwa`, `Storage`, `Pending` and receipt/document
  queue keys, but the new strings are still English placeholders until a
  translation pass; the PWA update description now says "pysplit" rather than
  the upstream name.

## 6. Intentionally deferred

- Authenticated two-device group claim/merge and queued login merge — Stage 11.
- Unified sync change rows for REST receipt/document writes — later sync
  hardening.
- Optional Background Sync registration, if the deployment wants it.
- Final deployment docs and PWA deployment/performance work — Stage 12.
