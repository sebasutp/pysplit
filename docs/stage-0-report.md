# Stage 0 report — scope and contracts

Date: 2026-10-24
Stages: 0A, 0B, 0C
Reference: `/workspace/spliit` (read-only mount)

## 0A — Reference source and baseline

### Files added

- `docs/reference-baseline.md`

No reference file was modified. Installs and test runs used a writable copy at
`/tmp/spliit-baseline/src` because the oracle is mounted read-only.

### Commands and observed output

| Command | Result |
|---|---|
| `node -v && npm -v` | `v24.21.0`, `11.19.0` |
| `DATABASE_URL=… npm ci` (copy) | **failed** at `postinstall`: Prisma `P3019`, schema `sqlite` vs `migration_lock.toml` `postgresql` |
| `npm ci --ignore-scripts` | exit 0 |
| `npx prisma generate` | exit 0, Prisma Client 7.9.1 |
| `npm rebuild better-sqlite3 @prisma/adapter-better-sqlite3` | exit 0 |
| `DATABASE_URL=… npx jest --ci` | `30 passed`, `353 passed`, 0 skipped, 2.498 s |
| `npx playwright test --list` | `Total: 41 tests in 14 files` |
| Playwright execution | **not runnable**: `docker: not installed`; `compose.e2e.yaml` requires PostgreSQL |
| `sqlite3 spliit-data/spliit.db` counts | Group 6, Participant 30, Category 44, Expense 122, ExpensePaidFor 473, ExpenseDocument 4, Activity 201, User 9, Account 5, UserGroup 6, Receipt 1, ReceiptItem 15, ReceiptItemPortion 10, ReceiptOptOut 1 |
| `sqlite3 spliit.db` counts | Group 296, Participant 370, Category **0**, Expense **0**, ExpenseDocument 128, User 602, Account 62, UserGroup 296 |
| Expense sum (primary DB) | `122` rows, `2767361` minor units, 5 distinct groups |
| `expenseDate` sample | `2026-09-03T11:23:49.573+00:00` |
| Boolean sample | `isReimbursement = 0` |

### `[VERIFY]` checklist

All ten items confirmed. One correction: `save-recent-group.tsx` lives under
`src/app/groups/[groupId]/`, not `src/app/groups/`. Details and the full table
are in `docs/reference-baseline.md` §3–§4.

### Gate checklist

- [x] Source and both databases exist and are readable.
- [x] Baseline report contains command output, not estimates.
- [x] Every `[VERIFY]` item has a confirmed or corrected value.
- [x] Jest baseline is green (30/30 suites, 353/353 tests).
- [ ] Playwright runtime results — **blocked by missing Docker**, documented as
      an environmental limitation. Spec discovery (41 tests / 14 files) is
      verified.

**Gate: PASSED with the documented environment limitation.**

## 0B — Inventory and executable parity matrix

### Files added

- `docs/parity-matrix.yml` — 111 rows (69 standard, 42 custom)
- `docs/parity-report.md` — generated view
- `scripts/check_parity_matrix.py` — discovery + validation + report generator

### Coverage

| Discovered reference behavior | Count | Mapped |
|---|---:|---:|
| Pages (`src/app/**/page.tsx`) | 14 | 14 |
| Procedure files (`*.procedure.ts` + admin/auth routers) | 28 | 28 |
| Jest suites (`*.test.ts(x)`) | 30 | 30 |
| Playwright specs (`e2e/*.spec.ts`) | 14 | 14 |

Rows also cover the HTTP route handlers (health, auth, S3 upload, CSV/JSON
exports), all 38 tRPC procedures (including the five inline sync procedures and
seven admin procedures), and the four new offline/admin/group-sync/PWA specs.

### Command and output

```bash
$ python3 scripts/check_parity_matrix.py
OK: 111 features; 14 pages, 28 procedure files, 30 Jest suites, 14 Playwright specs all mapped.
```

This host has no `python` alias, so `python3` (or the backend virtualenv)
was used. Both were run and produced the same output.

The checker fails on: a missing page/procedure/Jest/e2e mapping, duplicate IDs,
empty or TBD cells, unknown category/offline values, rows without tests, and a
missing reference tree. It regenerates `docs/parity-report.md` on success.

`pyyaml` is the only checker dependency; it is pinned in
`backend/requirements-dev.txt` and installed by CI.

### Gate checklist

- [x] Checker passes.
- [x] No `TBD` cells.
- [x] Every row names at least one test.
- [x] IDs are unique.
- [x] Every discovered page/procedure/suite/spec is mapped.

**Gate: PASSED.** Custom-feature rows are ready for product-owner review; the
list is `docs/parity-report.md`, filtered by class `custom`.

## 0C — Architecture decisions and contracts

### Files added

- `docs/adr/0000-decision-register.md`
- `docs/adr/0001-stack.md`
- `docs/adr/0002-offline-sync.md`
- `docs/adr/0003-auth.md`
- `docs/adr/0004-money-dates-ids.md`
- `docs/repository-contract.md`
- `docs/api.md`
- `docs/offline-capabilities.md`
- `docs/runbook-cutover.md`

### Decisions resolved (plan §8)

| # | Resolution |
|---|---|
| 1 | Plain `.jsx` + `checkJs` |
| 2 | Expense conflicts queued; metadata LWW |
| 3 | Memory access JWT + rotating HttpOnly refresh cookie |
| 4 | Local disk storage by default, S3/R2 adapter |
| 5 | Port existing receipt calculator + category inference |
| 6 | Short maintenance window |
| 7 | SQLite v1, SQLModel portable |
| 8 | Full offline editing; admin/AI online-only |

### Gate checklist

- [x] Four ADRs plus a decision register exist.
- [x] Repository contract defines methods, returns, errors, cancellation,
      pagination, ordering, mutation values and offline behavior.
- [x] API contract covers every resource in the matrix.
- [x] Offline capability matrix is explicit.
- [x] Cutover/rollback outline exists.
- [x] All eight open decisions are resolved with no remaining `TBD`.

**Gate: PASSED.** Acceptance is recorded in ADR 0000 on the basis of the
instruction to execute Stages 0–1; no contrary product decision was supplied.

## Deviations and open questions

1. `spliit/` was initially empty in this session; the complete source appeared
   before Stage 0A ran. The baseline verifies 57k files, both databases and all
   reference paths.
2. The reference `npm ci` is broken by a stale PostgreSQL
   `migration_lock.toml`. This is an upstream defect; Stage 2 does not reuse
   the Prisma migration history.
3. Playwright could not execute without Docker/PostgreSQL. Runtime parity will
   be established when the e2e stack is available; spec discovery is verified.
4. The second fixture database has zero categories and 128 orphan documents,
   confirming the importer's seeding and orphan-preservation requirements.
5. `pyyaml` is required by the parity checker. It is a dev-only dependency.

## Deferred to later stages

- Domain models and Alembic revisions (Stage 2).
- Domain math and golden fixtures (Stage 3).
- Auth/OAuth/tiers/admin API (Stage 4).
- REST resources (Stages 5A–5D).
- Sync protocol (Stage 6).
- Receipts/AI (Stage 7).
- SPA features, repository implementations, offline, PWA (Stages 8–11).
- Deployment and cutover (Stages 12–13).
