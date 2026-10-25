# Stage 8 report — Repository-based SPA, groups, expenses, balances, receipts and admin

Status: complete (Stages 8B, 8C and 8D). Stage 8A was committed previously.

## Files added or changed

### Repository and hooks

- `frontend/src/services/repository/contract.js` — added `receipts.upload`,
  `features.get`, and the admin method group to the frozen interface.
- `frontend/src/services/repository/online.js` — pass-through implementations
  for receipt upload, runtime feature flags, and admin metrics/users/groups.
- `frontend/src/hooks/useActiveUser.js`, `useGroup.js`, `useCategories.js`,
  `useExpenses.js`, `useBalances.js`, `useStats.js`, `useActivities.js`,
  `useFeatures.js` — all repository-backed, cancellable reads and reload actions.
- `frontend/src/utils/recent-groups.js` — added `hasPendingActiveUser`,
  `hasActiveUserKey`, and `clearPendingActiveUser` helpers.
- `frontend/src/utils/currency.js` — common currency list, labels, amount
  parsing and major/minor conversion.
- `frontend/src/utils/expenses.js`, `date-groups.js`, `stats-range.js`,
  `compress-image.js` — pure helpers for cards, lists, statistics and uploads.
- `frontend/src/schemas/expense.js` — zod expense-form schema ported from the
  reference validation, including split-mode and participant checks.

### UI

- `components/ui/Select.jsx` — accessible `combobox`/`listbox`/`option`
  primitive compatible with the ported Playwright helpers.
- `components/groups/GroupLayout.jsx`, `GroupHeader.jsx`,
  `ActiveUserDialog.jsx` — group shell, tabs, share link, visit recording and
  the “Who are you?” flow.
- `components/groups/GroupForm.jsx` — locked participants with expenses and
  edit-mode support.
- `components/expenses/ExpenseList.jsx`, `ExpenseCard.jsx`,
  `ExpenseForm.jsx`, `ReceiptScanButton.jsx` — list, search, date filters,
  date groups, category icons, reimbursement/document indicators, exports, all
  split modes, multi-currency, recurrence, documents, deletion, saved splitting
  defaults and receipt prefill.
- `components/receipts/ReceiptFooter.jsx` — provisional totals, reconciliation
  and apply action.
- `pages/group/ExpensesPage.jsx`, `ExpenseCreatePage.jsx`,
  `ExpenseEditPage.jsx`, `BalancesPage.jsx`, `StatsPage.jsx`,
  `ActivityPage.jsx`, `InformationPage.jsx`, `GroupSettingsPage.jsx`,
  `ReceiptItemsPage.jsx` — group screens.
- `pages/AdminPage.jsx` — metrics, user search/tier changes/preauthorization,
  deletion and group administration.
- `router.jsx` — nested group routes and `/admin`; all existing group URLs
  remain deep-linkable.

### Tests and tooling

- Ported Playwright specs: `core`, `expense-edit-delete`, `expense-variants`,
  `split-modes`, `multi-currency`, `recurrence`, `stats`, `stats-breakdown`,
  `reimbursements`, `repayment-currency`, `active-user`.
- New specs: `receipts.spec.ts`, `admin.spec.ts`.
- Updated `e2e/app.ts` with tier login helpers and a session-boot wait;
  adapted export assertions to the `/api/.../expenses/export.{csv,json}` routes.
- Vitest: `ExpenseForm.test.jsx` (splitting defaults),
  `ReceiptFooter.test.jsx` (provisional totals), `lib/compress-image.test.js`,
  `lib/utils.test.js`; moved `analytics.test.js` to the path in the parity
  matrix.
- `scripts/check_architecture.py` and `src/architecture.test.js` now require
  every Stage 8 end-to-end spec.
- `dev` enables the Stage 8D online features locally and raises the auth
  limiter for full-suite runs; production defaults are unchanged.
- `docs/repository-contract.md` documents receipt upload, features and admin
  methods.

## Commands run and output

```text
$ cd frontend && npm test -- --run
Test Files  10 passed (10)
     Tests  28 passed (28)

$ npm run lint
Found 0 warnings and 0 errors.

$ npm run typecheck
tsc -p jsconfig.json            # no diagnostics

$ npm run build
dist/assets/index-*.css     27.82 kB │ gzip:   6.04 kB
dist/assets/index-*.js   1,186.96 kB │ gzip: 297.77 kB
✓ built in 227ms

$ BASE_URL=http://127.0.0.1:5173 npx playwright test --workers=4
45 passed (40.0s)

$ cd .. && python3 scripts/check_architecture.py
OK: architecture boundaries, repository files, locales and e2e specs are consistent.

$ backend/.venv-work/bin/python scripts/check_parity_matrix.py
OK: 123 features; 14 pages, 28 procedure files, 30 Jest suites, 14 Playwright specs all mapped.
```

The Playwright browser in this sandbox was missing its system libraries
(`libnspr4`, `libnss3`, X11/ATK/GBM). They were extracted into
`/tmp/pwlibs` from Ubuntu Noble packages and the suite was run with
`LD_LIBRARY_PATH=/tmp/pwlibs/usr/lib/x86_64-linux-gnu:/tmp/pwlibs/lib/x86_64-linux-gnu`.
This is an environment workaround only; no repository file depends on it.

## Gate checklist

| Gate | Status |
|---|---|
| 8B: group/expense UI; `core`, `expense-edit-delete`, `expense-variants`, `split-modes`, `multi-currency`, `recurrence` green | PASS |
| 8B: UI balances match the API for every split mode | PASS |
| 8C: `global-balance`, `reimbursements`, `repayment-currency`, `stats`, `stats-breakdown`, `active-user` green | PASS |
| 8C: locale keys for new screens present in every locale | PASS (`check_architecture.py`) |
| 8D: `receipts.spec.ts` and `admin.spec.ts` green | PASS |
| 8D: full online Playwright suite green (PWA reserved for Stage 10) | PASS (45/45) |
| Every hook/component imports the repository, never `api.js` | PASS (`check_architecture.py`) |
| Deep links load directly | PASS (`auth.spec.ts` and `core`) |

## Deviations and open questions

- The receipt end-to-end specs exercise the editor, the no-linked-receipt state
  and the server-disabled state. They do not call a live AI provider: no key is
  available in this environment. AI extraction, item assignment, apply
  invariants and provisional totals remain covered by the Stage 7 backend tests
  and the `ReceiptFooter` Vitest test.
- Reference exports used page-relative paths (`/groups/.../expenses/export/csv`).
  The REST API exposes `/api/groups/.../expenses/export.csv`; only the test
  request paths were adapted. User-visible group URLs are unchanged.
- `admin.spec.ts` is listed under Stage 11 in the parity matrix, but the admin
  UI and its online spec are delivered here as required by Stage 8D. Stage 11
  still owns two-device sync polish.
- PWA tests and offline behaviour are intentionally deferred to Stages 9–10.

## Deferred

- Dexie/IndexedDB reads, outbox and offline conflict handling (Stages 9A–9C).
- Workbox precache, install prompt and offline boot (Stage 10).
- Two-device authenticated group synchronization (Stage 11).
- Queued offline document/receipt uploads (Stage 10B).
