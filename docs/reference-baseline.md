# Reference baseline (Stage 0A)

Date: 2026-10-24
Reference tree: `/workspace/spliit` (kept read-only; git HEAD `c4ccb8b`)
Host tools: Node `v24.21.0`, npm `11.19.0`, Python `3.12.3`

This document records **observed** facts about the reference fork. Anything not
reproduced by the commands below is not used as a baseline.

## 1. Source completeness

`spliit/` contains the complete fork source: Next.js app, Prisma schema and
migrations, tRPC routers, Jest tests, Playwright specs, 35 locale files,
design documents, and both fixture databases.

Notable top-level evidence:

```
src/app/**/page.tsx            14 pages
src/trpc/routers/**           26 *.procedure.ts files + admin/auth routers
src/**/*.test.ts(x)           30 Jest suites
e2e/*.spec.ts                 14 Playwright specs
messages/*.json               35 locale files
prisma/schema.prisma          17 models
design.md, design-receipt-items.md
spliit-data/spliit.db, spliit.db
```

The tree is mounted **read-only** in this environment. All installs and test
runs were therefore performed on a writable copy (`rsync` excluding
`node_modules`, `.next`, `.git`, `.jj`, `build`, `dist`) at
`/tmp/spliit-baseline/src`. No reference file was modified.

## 2. Commands and observed output

### 2.1 Clean install

```bash
cd /tmp/spliit-baseline/src
DATABASE_URL=file:/tmp/spliit-baseline/npmci.db npm ci
```

Observed: **fails** in the `postinstall` hook.

```
25 migrations found in prisma/migrations

Error: P3019

The datasource provider `sqlite` specified in your schema does not match the
one specified in the migration_lock.toml, `postgresql`. Please remove your
current migration directory and start a new migration history with prisma
migrate dev. Read more: https://pris.ly/d/migrate-provider-switch

npm error command sh -c prisma migrate deploy && prisma generate
```

Cause: `prisma/schema.prisma` declares `provider = "sqlite"` while
`prisma/migrations/migration_lock.toml` still says `provider = "postgresql"`.
This is an upstream artifact of the fork: `README.md` and `compose.e2e.yaml`
still describe PostgreSQL, while `compose.yaml` and the shipped databases use
SQLite. It is a reference defect, not an environment failure.

Workaround used for the baseline, and recorded as a deviation:

```bash
npm ci --ignore-scripts          # exit 0
npx prisma generate              # exit 0, Prisma Client 7.9.1
npm rebuild better-sqlite3 @prisma/adapter-better-sqlite3   # exit 0
```

The rebuild is required because `--ignore-scripts` skips the native
`better-sqlite3` build used by the database-backed tests.

### 2.2 Jest

```bash
DATABASE_URL=file:/tmp/spliit-baseline/jest.db npx jest --ci
```

Observed output (final lines):

```
Test Suites: 30 passed, 30 total
Tests:       353 passed, 353 total
Snapshots:   0 total
Time:        2.498 s
```

Result: **30/30 suites, 353/353 tests passed, 0 skipped.** No test was
modified or excluded. `.test.tsx` suites are included (28 `.test.ts` + 2
`.test.tsx` = 30).

### 2.3 Playwright

```bash
npx playwright test --list
```

Observed output (final line):

```
Total: 41 tests in 14 files
```

Execution was **not possible** in this environment: `scripts/e2e.sh` requires
Docker (`docker: not installed` in the sandbox) and `compose.e2e.yaml` starts a
PostgreSQL service. The 41 tests were parsed successfully, so spec syntax and
discovery are verified; runtime results are deferred to a Docker-capable host.

Environmental failure recorded, not a source failure.

### 2.4 Fixture databases

Both databases are readable with `sqlite3`.

#### `spliit/spliit-data/spliit.db` (primary fixture)

| Table | Rows |
|---|---:|
| Group | 6 |
| Participant | 30 |
| Category | 44 |
| Expense | 122 |
| ExpensePaidFor | 473 |
| ExpenseDocument | 4 |
| Activity | 201 |
| RecurringExpenseLink | 0 |
| User | 9 |
| Account | 5 |
| Session | 0 |
| VerificationToken | 0 |
| UserGroup | 6 |
| Receipt | 1 |
| ReceiptItem | 15 |
| ReceiptItemPortion | 10 |
| ReceiptOptOut | 1 |

Additional checks:

```
Expense count: 122
Expense amount sum (minor units): 2767361
Distinct groups referenced by expenses: 5
```

This matches the plan's expected "6 groups, 122 expenses, 1 receipt".

#### `spliit/spliit.db` (larger fixture)

| Table | Rows |
|---|---:|
| Group | 296 |
| Participant | 370 |
| Category | **0** |
| Expense | **0** |
| ExpenseDocument | 128 (orphans) |
| User | 602 |
| Account | 62 |
| UserGroup | 296 |
| all other tables | 0 |

This matches the plan's expected "296 groups, 0 expenses" and confirms the
plan's warning that `Category` can be empty and must be seeded on import.
`ExpenseDocument` rows without `Expense` rows confirm orphan documents exist.

Data-format spot checks in the primary fixture:

```
expenseDate: 2026-09-03T11:23:49.573+00:00   (ISO text with offset)
isReimbursement: 0                          (SQLite boolean)
conversionRate: ''                          (DECIMAL stored as text/numeric)
amount: 159600                              (integer minor units)
```

## 3. `[VERIFY]` checklist

| Item | Status | Observed value |
|---|---|---|
| Next.js 16 App Router, React 19, TypeScript | Confirmed | `next ^16.3.2`, `react ^19.2.8`, `typescript ^6.0.3`, `src/app/**/page.tsx` |
| tRPC 11 + superjson | Confirmed | `@trpc/* ^11.18.0`, `superjson ^2.2.6`, `src/trpc/routers/**` |
| Prisma + SQLite, ~17 models | Confirmed with discrepancy | `prisma/schema.prisma` provider `sqlite`, 17 models; `migration_lock.toml` says `postgresql` (stale) |
| HMAC-SHA256 JWT in `spliit_session` cookie | Confirmed | `src/lib/auth/session.ts`: `createHmac('sha256', secret)`, `SESSION_COOKIE_NAME = 'spliit_session'`, tier reloaded from DB per request |
| Google/GitHub OAuth | Confirmed | `src/lib/auth/oauth.ts`, `src/app/api/auth/[...auth]/route.ts` (`signin`, `callback`, `session`, `signout`, dev `mock-login`) |
| Tailwind 4, shadcn/Radix, next-intl, ~35 locales | Confirmed | `tailwindcss ^4.3.2`, Radix packages, `next-intl ^4.13.7`, 35 files in `messages/` |
| TanStack Query + SWR; localStorage prefs | Confirmed | `@tanstack/react-query`, `swr`; recent/starred/archived and `*-activeUser` keys in `recent-groups-helpers.ts`, `active-user-modal.tsx`, `expense-form.tsx` |
| PWA caches assets/pages only, `/api` network-only | Confirmed | `public/sw.js` returns early for `/api/`, network-first navigations, cache-first static assets, offline fallback |
| OpenAI-compatible AI: total, items, category | Confirmed | `src/lib/ai/client.ts` (`AI_*` over `OPENAI_*`), `ai/prompts.ts`, `ai/schemas.ts`, models `gpt-5-nano` defaults |
| Jest ~30 files; Playwright 14 specs; Docker e2e | Confirmed | 30 suites / 353 tests; 14 specs / 41 tests; `compose.e2e.yaml` + `scripts/e2e.sh` (Docker required) |
| Fixture data volumes | Confirmed | 6/122/1 and 296/0 as above; second DB has 0 categories and 128 orphan documents |

## 4. Reference-path corrections for §1.4

All paths in §1.4 resolve except one:

| Plan path | Actual path |
|---|---|
| `spliit/src/app/groups/save-recent-group.tsx` | `spliit/src/app/groups/[groupId]/save-recent-group.tsx` |

Everything else, including `src/components/service-worker-registration.tsx`,
`src/app/manifest.ts`, and `create-from-receipt-button-actions.ts`, exists at
the listed location.

## 5. Discrepancies and open baseline questions

1. **Migration provider mismatch.** Schema is SQLite, `migration_lock.toml` is
   PostgreSQL, README/compose.e2e assume PostgreSQL. The shipped runtime
   (`compose.yaml`) and both fixture databases are SQLite. Stage 2 must not
   reuse the reference migration history; it builds Alembic migrations from
   the SQLite schema and the real databases.
2. **`npm ci` is not reproducible as-is** because of the failing `postinstall`.
   This does not affect Jest, which passes after `prisma generate`.
3. **Playwright could not be executed** without Docker/PostgreSQL. The suite is
   enumerated but its green/red status is unverified on this host.
4. **`.env` is masked** by the sandbox (a non-regular file). Every command above
   passed `DATABASE_URL` explicitly. The reference `.env.example` is readable
   and is the source of variable names.
5. **Second fixture has no categories.** Import must seed the 44 defaults, as
   required by the plan.
6. **No `RecurringExpenseLink` rows exist** in either fixture, so recurrence
   import cannot be validated against real data yet; Stage 2's synthetic
   fixture must cover it.

## 6. Baseline verdict

The source, design documents, schemas, tests, and both fixture databases are
present and readable. The behavioral oracle is usable. The Stage 0A gate is
**passed with the deviations listed in §5**, which are recorded rather than
worked around silently.
