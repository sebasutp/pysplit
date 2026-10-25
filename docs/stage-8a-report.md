# Stage 8A report — repository-based SPA shell, auth, group list

Date: 2026-10-25
Stage: 8A (the first bounded part of Stage 8; 8B–8D are not included)

## Outcome

The SPA now has a working online shell built on the frozen repository contract:

- `services/repository/contract.js` documents the full method surface,
  `RepositoryError`, method enumeration and the shared `run()` error boundary.
- `services/repository/online.js` implements that contract as a thin
  pass-through over `services/api.js` (auth, groups, participants, categories,
  expenses, balances, statistics, activities, receipts, documents, exports and
  the online sync placeholders).
- `services/repository/index.js` is the only module components and hooks
  import. `services/api.js` now supports in-memory bearer tokens, one automatic
  refresh-and-retry on 401, rotating-refresh single-flight protection, CSRF
  double-submit headers and text/file responses for exports.
- i18next is configured with all 35 ported locale files. Every locale has the
  same 450-key set as `en-US`; missing reference translations are filled from
  English and keys removed upstream are dropped.
- The shell has a header, locale switcher, theme toggle, user menu, toasts,
  login dialog, accessible empty/loading/error states, and the routes frozen by
  the plan, including the `/groups/:groupId` → expenses redirect.
- The group list supports recent, starred and archived groups, add-by-URL,
  remove, star/archive actions, participant/date metadata and the cross-group
  balance card. Group creation is tier-aware: anonymous visitors are prompted
  to sign in, `sync_users` see approval messaging, and `group_creators`/`admin`
  get the create form.
- Playwright is configured with a `BASE_URL` override; the reference seeding
  helpers and Stage 8A specs are ported. `auth.spec.ts` covers the login gate,
  approval tier and direct shared-link loading.
- `scripts/check_architecture.py` enforces backend router/pure-util boundaries,
  the frontend repository boundary, no `dangerouslySetInnerHTML`, locale key
  parity, repository files and required e2e specs.

## Files added

### Repository and services

- `frontend/src/services/repository/contract.js`
- `frontend/src/services/repository/online.js`
- `frontend/src/services/repository/index.js`
- `frontend/src/services/i18n.js`

### Hooks

- `frontend/src/hooks/useAuth.jsx`
- `frontend/src/hooks/useGroups.js`
- `frontend/src/hooks/useGlobalBalance.js`
- `frontend/src/hooks/useTheme.js`
- `frontend/src/hooks/useToast.jsx`

### Components

- `frontend/src/components/auth/LoginDialog.jsx`
- `frontend/src/components/auth/UserMenu.jsx`
- `frontend/src/components/common/States.jsx`
- `frontend/src/components/groups/AddGroupByUrlButton.jsx`
- `frontend/src/components/groups/GlobalBalanceCard.jsx`
- `frontend/src/components/groups/GroupForm.jsx`
- `frontend/src/components/groups/RecentGroupList.jsx`
- `frontend/src/components/groups/RecentGroupListCard.jsx`
- `frontend/src/components/layout/Footer.jsx`
- `frontend/src/components/layout/Header.jsx`
- `frontend/src/components/system/LocaleSwitcher.jsx`
- `frontend/src/components/system/ThemeToggle.jsx`
- `frontend/src/components/ui/Button.jsx`
- `frontend/src/components/ui/Card.jsx`
- `frontend/src/components/ui/Dialog.jsx`
- `frontend/src/components/ui/Feedback.jsx`
- `frontend/src/components/ui/Form.jsx`
- `frontend/src/components/ui/Input.jsx`

### Pages, utilities and locales

- `frontend/src/pages/GroupsPage.jsx`
- `frontend/src/pages/CreateGroupPage.jsx`
- `frontend/src/pages/PlaceholderPage.jsx`
- `frontend/src/utils/analytics.js`
- `frontend/src/utils/currency.js`
- `frontend/src/utils/recent-groups.js`
- `frontend/src/locales/messages/*.json` (35 files)
- `frontend/scripts/sync-locales.mjs`

### Tests and tooling

- `frontend/src/services/repository/contract.test.js`
- `frontend/src/components/ui/Form.test.jsx`
- `frontend/src/utils/analytics.test.js`
- `frontend/src/architecture.test.js`
- `frontend/playwright.config.ts`
- `frontend/e2e/app.ts`
- `frontend/e2e/fixtures.ts`
- `frontend/e2e/ui.ts`
- `frontend/e2e/group-management.spec.ts`
- `frontend/e2e/global-balance.spec.ts`
- `frontend/e2e/auth.spec.ts`
- `scripts/check_architecture.py`
- `docs/stage-8a-report.md`

## Files changed

- `frontend/src/App.jsx` — providers and shell composition.
- `frontend/src/router.jsx` — real pages plus frozen deep-link routes.
- `frontend/src/App.test.jsx` — group shell, redirect and auth-gate tests.
- `frontend/src/services/api.js` — bearer tokens, refresh vector, CSRF, text
  responses, error retry.
- `frontend/src/test/setup.js` — jsdom `matchMedia`.
- `frontend/vite.config.js` — Vitest only scans `src/**`.
- `frontend/jsconfig.json` — Node types and no node_modules JS checking.
- `frontend/package.json`, `frontend/package-lock.json` — i18next,
  react-i18next, zod, Playwright and `@types/node`; `e2e` and `locales:sync`
  scripts.
- `Makefile`, `.github/workflows/ci.yml` — architecture check target/step.
- `.gitignore` — ignore the sandbox Playwright library cache.
- Deleted Stage 1 scaffolding that bypassed the repository boundary:
  `frontend/src/components/system/HealthIndicator.jsx` and
  `frontend/src/components/common/PagePlaceholder.jsx`.

No backend production code was changed.

## Design details

### Auth transport

`api.js` owns the access token in memory. A refresh is shared by all concurrent
callers so React StrictMode's double mount cannot rotate the same refresh token
twice and trigger family revocation. On a 401 from an authenticated request the
client refreshes once and replays the request; `/auth/*` calls never recurse.
Refresh/logout send the readable `pysplit_csrf` cookie in `X-CSRF-Token` and
rely on the browser's `Origin` header for the API's same-origin check.

`AuthProvider` refreshes on boot, then calls `/auth/me` to load the user and
provider discovery. A missing session becomes anonymous; a network failure does
not crash the shell. Login redirects through the backend OAuth start endpoint
with a relative `return_to`; logout revokes the refresh token and clears state.

### Group list and membership

The group list reads the same localStorage keys as the reference
(`recentGroups`, `starredGroups`, `archivedGroups`) so existing profiles keep
their list. It then calls `POST /groups/sync` with local IDs and star/archive
arrays. Authenticated responses become the canonical list and are written back
to localStorage; anonymous responses preserve the local list. Star/archive
mutations update local state immediately and call the membership API when the
user is authenticated. Group creation writes the new ID to the recent list and
sets `newGroup-activeUser` to `None`.

### Global balance

The card uses `${groupId}-activeUser` for every listed group and calls
`GET /balances?groups=group:participant,...`. Amounts are aggregated per
currency (codes cannot be summed), formatted with `Intl.NumberFormat`, and the
card stays hidden until at least one group has an active user.

### Locales

The reference translation files are partial. `scripts/sync-locales.mjs` keeps
only keys present in `en-US`, fills missing values from English, and preserves
existing translations. This makes key parity machine-checkable now and keeps
every translated string that upstream provides.

## Verification commands and output

### Frontend unit, lint, typecheck and build

```bash
$ cd frontend
$ npm test -- --run
...
 Test Files  6 passed (6)
      Tests  24 passed (24)

$ npm run lint
Found 0 warnings and 0 errors.
Finished in 8ms on 46 files with 97 rules using 24 threads.

$ npm run typecheck
> tsc -p jsconfig.json
(no errors)

$ npm run build
...
dist/assets/index-KIIc08Pc.js   1,102.51 kB │ gzip: 277.78 kB
✓ built in 206ms
```

The build emits Vite's >500 kB raw-chunk warning. The gzip total is 277.78 kB,
below the plan's 300 kB initial-JavaScript target; route-level splitting and
lazy locale loading remain Stage 12 work.

### Architecture and parity

```bash
$ python3 scripts/check_architecture.py
OK: architecture boundaries, repository files, locales and e2e specs are consistent.

$ python3 scripts/check_parity_matrix.py
OK: 123 features; 14 pages, 28 procedure files, 30 Jest suites, 14 Playwright specs all mapped.
```

### Backend architecture regression

```bash
$ cd backend
$ PYTHONPATH=. .venv/bin/pytest tests/test_architecture.py -q
8 passed, 1 warning in 1.11s
```

### Stage 8A Playwright command

The sandbox image lacks the Chromium system libraries (`libnspr4`, `libnss3`,
X11/ATK/GBM). They were extracted from Ubuntu noble packages into the ignored
`/workspace/.cache/libs` directory; no repository files were changed. The
actual command therefore prefixed `LD_LIBRARY_PATH`:

```bash
$ cd frontend
$ LIBPATH=$(cat /workspace/.cache/libs/path.txt)
$ LD_LIBRARY_PATH="$LIBPATH" BASE_URL=http://127.0.0.1:5173 \
    npx playwright test e2e/group-management.spec.ts \
    e2e/global-balance.spec.ts --grep "Recent groups|global" --workers=1
Running 5 tests using 1 worker
  ✓ global-balance.spec.ts:13 sums balances across groups once you are identified in them
  ✓ global-balance.spec.ts:49 reports being settled up when every balance is zero
  ✓ global-balance.spec.ts:73 stays hidden until you say who you are
  ✓ group-management.spec.ts:59 lists visited groups under Recent groups
  ✓ group-management.spec.ts:74 shows no recent groups in a fresh browser profile
5 passed (7.6s)
```

Authentication and deep-link coverage:

```bash
$ LD_LIBRARY_PATH="$LIBPATH" BASE_URL=http://127.0.0.1:5173 \
    npx playwright test e2e/auth.spec.ts --workers=1
  ✓ asks anonymous visitors to sign in before creating a group
  ✓ shows approval messaging for sync users
  ✓ loads shared group deep links directly
3 passed (2.4s)
```

### Dependency audit

```bash
$ npm audit --audit-level=high
found 0 vulnerabilities
```

## Gate checklist

| Gate item | Status |
|---|---|
| `repository/contract.js` and `repository/online.js` implement the documented interface | Pass |
| Hooks and components import only `repository/index.js` | Pass (`check_architecture.py` + `architecture.test.js`) |
| `/` redirects to `/groups`; group list and create routes work | Pass |
| Group deep-link routes resolve directly and `/groups/:groupId` redirects to expenses | Pass |
| Header, locale switcher, theme toggle, user menu and toasts | Pass |
| Login dialog with provider discovery and tier-aware group creation | Pass |
| Anonymous, sync-user approval and creator paths | Pass (`auth.spec.ts`) |
| Recent, starred and archived groups; add by URL; remove; star/archive | Pass |
| Cross-group balance card with per-currency aggregation | Pass |
| Loading, error and empty states with accessible labels | Pass |
| 35 locale files and enforced key parity | Pass |
| Reference seeding helpers and Stage 8A specs ported | Pass |
| Playwright `BASE_URL` override | Pass |
| `npm test`, lint, typecheck and build | Pass |
| Architecture and parity checkers | Pass |
| Online groups/auth e2e and direct deep links | Pass |

**Gate: PASSED.**

## Deviations and open questions

1. **Only Stage 8A was implemented.** Group headers/tabs, expenses, balances,
   statistics, receipts and admin UI remain in 8B–8D as planned.
2. **Global-balance e2e seeds expenses through the public API.** The expense
   form is Stage 8B, but the plan's Stage 8A command includes the
   `global-balance` spec. The assertions and selectors are unchanged; only the
   seeding call uses `addExpenseViaApi`. The UI-driven `addExpense` helper is
   already ported for 8B.
3. **`setActiveUser` writes the per-group key directly for now.** The reference
   helper relies on the expense screen migrating `newGroup-activeUser`; that
   migration is Stage 9C. The helper now resolves the participant ID through
   the group API and writes `<groupId>-activeUser`.
4. **Playwright depends on user-space browser libraries in this sandbox.** The
   gate command required `LD_LIBRARY_PATH`; CI on a standard Ubuntu runner uses
   `npx playwright install --with-deps` equivalent provisioning and needs no
   workaround.
5. **`/` is a redirect, not the reference landing page.** This follows the
   Stage 8A deliverable and preserves `/groups` as the effective home.
6. **Locales are eager resources, and partial translations are English-filled.**
   The reference files are incomplete (up to 394 missing keys). Filling them
   keeps the UI complete and parity enforceable; translated values that exist
   are untouched.
7. **The repository is online-only at this stage.** `local.js`, Dexie and the
   outbox arrive in 9A/9B; the contract test currently validates the online
   implementation only.
8. **The e2e helper uses `POST /api/auth/mock-login`.** Group creation requires
   the fork's `group_creators` tier, unlike upstream Spliit's accountless flow.
   The helper is development/test-only and is not reachable in production.
9. **The Stage 1 health indicator was removed.** It imported `api.js` from a
   component, which the new repository boundary forbids. Health remains
   available at `/api/health` and is covered by backend tests.

## Intentionally deferred

- Group header/tabs, information/edit pages, participant management, expense
  list/form, activity exports (8B).
- Balances and statistics screens, active-user modal and mark-as-paid (8C).
- Receipts, smart split and admin dashboard UI (8D).
- Dexie repository, outbox, offline calculations and localStorage migration
  (9A–9C).
- PWA installation/offline boot (10A–10B).
- Route-level bundle splitting and lazy locale loading (Stage 12 performance
  work).
