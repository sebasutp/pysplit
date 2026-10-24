# Spliit → FastAPI + React: Staged Migration Plan

> Goal: replace the Next.js/tRPC/Prisma app in `spliit/` with a Python/FastAPI
> backend and a React/Vite SPA (**pysplit**) while preserving standard Spliit
> behavior, every existing shared-group URL, and the fork's custom features:
> account login, tiered permissions, cross-device group sync, admin tools,
> AI-assisted receipt splitting, category inference, and optional S3/R2
> document storage.

The application is **offline-first**: once a group has been synchronized, users
can read and edit its data without a network connection. Pending edits are
stored durably in IndexedDB and synchronized later with explicit conflict
handling.

This plan is written for a smaller ("flash") model to execute **one bounded
stage per session**. Every stage has an explicit scope, reference files,
deliverables, verification commands, and a gate. Do not start the next stage
until the current gate passes.

---

## Milestones

- **M0 — Scope and contracts (Stages 0A–0C):** verify the reference source,
  freeze the parity matrix, and agree on architecture and synchronization
  contracts.
- **M1 — Online parity (Stages 1–8D):** the new stack replaces the old one
  feature-for-feature online. This milestone is shippable on its own, but it
  is not yet fully offline-capable.
- **M2 — Offline and PWA (Stages 9–10):** IndexedDB repository, durable
  outbox, conflict handling, local calculations, installable PWA, and offline
  UX. The stable repository interface introduced in Stage 8A keeps these
  changes from rewriting components and hooks.
- **M3 — Login sync, cutover, and retirement (Stages 11–13):** authenticated
  group synchronization, production deployment and rollback rehearsal, and
  retirement of the Node application.

---

## 0. How to use this plan

1. Pick exactly one stage. Read the stage's "Read first" files before writing
   code.
2. Implement only the deliverables listed for that stage. No opportunistic
   refactors and no libraries outside the agreed stack.
3. Run the verification commands. Record real command output in the stage
   report.
4. Stop when the gate passes. Do not begin the next stage, even if the current
   one was easy.
5. If a required reference file or fixture is missing, stop and report it.
   Do not infer behavior that cannot be verified against the source.

### Stage-report format

Every stage report must include:

- files added or changed;
- exact commands run and their output;
- the gate checklist with pass/fail status;
- deviations from the plan and open questions;
- anything intentionally deferred to a later stage.

### Legend

- **Gate** = objective evidence that the stage is safe to build on.
- **Parity** = the same observable behavior as the reference application.
- **Golden fixture** = deterministic JSON captured from the reference
  implementation and replayed against Python and JavaScript implementations.
- **Feature ID** = a stable identifier in `docs/parity-matrix.yml` that links a
  reference behavior to its target implementation and verification test.

---

## 1. Reference application and preservation requirements

### 1.1 Reference stack — verify during Stage 0A

The expected reference stack is listed below. Every item marked `[VERIFY]`
must be confirmed or corrected against the actual source before Stage 0B.

| Area | Expected implementation |
|---|---|
| Web framework | Next.js 16 App Router, React 19, TypeScript `[VERIFY]` |
| API | tRPC 11 (`src/trpc/routers/*`), superjson `[VERIFY]` |
| Database | Prisma + SQLite, approximately 17 models `[VERIFY]` |
| Auth | Custom HMAC-SHA256 JWT in `spliit_session` cookie, Google/GitHub OAuth `[VERIFY]` |
| UI | Tailwind 4, shadcn/Radix components, next-intl, approximately 35 locale files `[VERIFY]` |
| Client data | TanStack Query + SWR; localStorage for recent/starred/archived groups and active user |
| PWA | `public/sw.js` caches assets and pages only; `/api` traffic is network-only |
| AI | OpenAI-compatible Chat Completions: receipt total, receipt line items, category from title `[VERIFY]` |
| Tests | Jest, approximately 30 files; Playwright, 14 specs; Docker e2e stack `[VERIFY]` |
| Data | `spliit-data/spliit.db`: 6 groups, 122 expenses, 1 receipt; larger `spliit.db`: 296 groups, 0 expenses `[VERIFY]` |

### 1.2 Standard Spliit features to preserve

- Create, edit, and share groups by URL.
- Group information, participant management, and group tabs.
- Expense create/edit/delete with date, title, category, notes, documents,
  reimbursement flag, and paid-for participants.
- Split modes: `EVENLY`, `BY_SHARES`, `BY_PERCENTAGE`, and `BY_AMOUNT`.
- Multi-currency expenses with conversion rates.
- Recurrence: `NONE`, `DAILY`, `WEEKLY`, and `MONTHLY`.
- Balances, public balances, suggested reimbursements, and "mark as paid".
- Stats: totals, personal totals, spending over time, by participant, by
  category, recurring spending, date-range filtering, and drill-downs.
- Activity log and CSV/JSON exports.
- Active user per group and global balance across groups.
- Recent, starred, and archived groups.
- Seeded categories, currently expected to be 44.
- Existing shared-group URLs and route behavior.
- Installable PWA and an offline application shell.

### 1.3 Custom fork features to preserve

- Accounts with Google and GitHub OAuth.
- Tiers: `sync_users`, `group_creators`, and `admin`.
- Admin dashboard and admin bootstrap CLI.
- Cross-device group synchronization after login.
- Local guest groups merge into the account without duplication.
- Star/archive state synchronizes across devices.
- Group access is recorded when a group is visited.
- Receipt scan extracts the total from an image.
- Receipt line items ("smart split") extract items and charges, support
  fractional assignment and opt-outs, show provisional totals, and can be
  applied to an expense.
- AI infers an expense category from its title.
- Optional S3/R2-compatible document storage.

### 1.4 Reference files by area

Confirm these paths in Stage 0A before relying on them.

| Area | Read first |
|---|---|
| Domain math | `spliit/src/lib/shares.ts`, `balances.ts`, `totals.ts`, `receipt-split.ts`, `receipt-apply.ts`, `currency-conversion.ts`, `date-groups.ts` |
| Validation | `spliit/src/lib/schemas.ts`, `enums.ts` |
| Data access | `spliit/src/lib/api.ts`, including recurrence materialization |
| API surface | `spliit/src/trpc/routers/**/*.ts`, `_app.ts`, `init.ts` |
| Auth and tiers | `spliit/src/lib/auth/*`, `spliit/src/trpc/init.ts`, `spliit/src/trpc/routers/admin/index.ts`, `design.md` |
| Group sync | `spliit/src/trpc/routers/groups/sync.procedure.ts`, `spliit/src/app/groups/recent-group-list.tsx`, `recent-groups-helpers.ts`, `save-recent-group.tsx` |
| Receipts and AI | `spliit/src/lib/ai/*`, `receipt-extraction.ts`, `receipts.ts`, `spliit/src/trpc/routers/groups/receipts/*`, `create-from-receipt-button-actions.ts`, `design-receipt-items.md` |
| UI behavior | `spliit/src/app/**/page.tsx`, `spliit/src/components/**`, `spliit/messages/*.json` |
| PWA | `spliit/public/sw.js`, `spliit/src/components/service-worker-registration.tsx`, `spliit/src/app/manifest.ts`, `spliit/e2e/pwa.spec.ts` |
| Behavioral specification | `spliit/e2e/*.spec.ts`, `spliit/src/**/*.test.ts` |

### 1.5 Important data-format facts

- Prisma SQLite stores `DateTime` as ISO text, for example
  `2026-09-03T11:23:49.573+00:00`.
- Booleans are stored as `0` or `1`.
- `Decimal` conversion rates are stored as text or numeric values. Import with
  Python `Decimal`, never `float`.
- IDs are nanoid strings, not UUIDs. Preserve legacy IDs so shared links keep
  working.
- Money is represented as integer minor units. Quantities are integer
  thousandths.
- `ExpenseDocument.expenseId` is nullable; orphan documents exist.
- `Activity` has no foreign key to `Expense`; orphan activities exist.
- `Category` may be empty in a database. Seed the 44 defaults if missing.
- `Session` and `VerificationToken` are not migrated; users log in again.
- `UserGroup` and `ExpensePaidFor` are composite-key join tables.
- `Receipt` is unique on `(groupId, imageUrl)`.
- `expenseDate` stores a full timestamp, but the UI and statistics treat it as
  a UTC date. Keep the timestamp internally to preserve ordering and expose
  `YYYY-MM-DD` at the API boundary.

---

## 2. Target architecture

### 2.1 Stack

| Layer | Choice |
|---|---|
| API | FastAPI + Uvicorn |
| Data | SQLModel (SQLAlchemy 2) + Alembic migrations |
| Validation | Pydantic v2 at the HTTP boundary |
| Auth | JWT access token plus rotating refresh cookie; Google/GitHub OAuth |
| Backend tests | pytest + pytest-xdist, in-memory SQLite |
| Backend quality | Ruff linting and formatting; coverage of changed code; `pip-audit` |
| Frontend | React + Vite, plain `.jsx` |
| Frontend forms | zod, ported from the reference schemas |
| Frontend data | Native `fetch` behind one `services/api.js`; feature hooks; repository boundary; no axios/react-query |
| Offline data | Dexie/IndexedDB local-first repository plus outbox |
| PWA | `vite-plugin-pwa` / Workbox |
| Frontend tests | Vitest + Testing Library + jsdom; Playwright e2e |
| Frontend quality | oxlint; `tsc -p jsconfig.json` with `checkJs`; `npm audit` |
| i18n | i18next + react-i18next, approximately 35 locale files |
| Deployment | Docker Compose: `api` plus `web` (nginx serving Vite and proxying `/api`) |

### 2.2 Repository layout

```text
/workspace
  backend/
    app/
      main.py                 # create app, middleware, include routers
      api/                    # routers and deps.py; HTTP only
      models/                 # SQLModel table classes, one per file
      schemas/                # Pydantic request and response models
      services/               # business logic and transactions
      storage/                # local and S3 blob I/O
      formats/                # CSV and JSON export
      core/                   # config, database, security, OAuth, middleware, limits
      utils/                  # pure domain functions
      scripts/                # importer, verifier, admin bootstrap
    alembic/
    tests/
    requirements.txt
    requirements-dev.txt
    alembic.ini
    pytest.ini
    ruff.toml
  frontend/
    src/
      main.jsx  App.jsx  router.jsx
      components/<feature>/   # presentational UI, one component per file
      hooks/                  # loading, errors, cancellation, sync status
      services/
        api.js                # sole HTTP client
        config.js
        db.js                 # Dexie schema
        outbox.js
        sync.js
        repository/
          contract.js         # documented repository contract
          index.js
          online.js
          local.js
      utils/                  # pure JavaScript mirrors of domain logic
      locales/messages/       # ported locale files
      styles/
    e2e/
    vite.config.js
    package.json
    jsconfig.json
  shared/
    fixtures/
      domain/
      http/
      legacy/
  scripts/
    check_parity_matrix.py
    check_architecture.py
  docs/
    parity-matrix.yml
    parity-report.md
    api.md
    repository-contract.md
    sync-protocol.md
    offline-capabilities.md
    adr/
    runbook-cutover.md
  dev
  compose.yaml
  Dockerfile.api
  Dockerfile.web
  .env.example
```

Keep `spliit/` unchanged as the behavioral oracle until Stage 13, except for
the temporary fixture-export scripts explicitly listed below.

### 2.3 Repository-first frontend architecture

The UI is built against a stable repository interface from Stage 8A:

```text
component → hook → repository interface
                         ├─ M1: online repository → api.js → fetch
                         └─ M2: local repository → Dexie + outbox → sync.js
```

Rules:

- Hooks and components import only the repository interface, never `api.js`
  directly.
- The interface covers groups, participants, expenses, balances, statistics,
  receipts, categories, and user-group membership.
- It specifies cancellation, pagination, ordering, errors, and the canonical
  value returned by mutations.
- The online implementation is a thin pass-through during M1.
- The local implementation reads and writes IndexedDB during M2.
- Components and hooks remain unchanged when the local implementation replaces
  the online implementation.

This prevents the offline milestone from becoming a frontend rewrite.

### 2.4 Offline architecture

```text
component → hook → repository → IndexedDB
                             │
                             └─ outbox → sync.js → api.js → FastAPI
```

- Every read comes from IndexedDB, so the UI works offline and after reload.
- Every write is applied locally and appended to the outbox in the same Dexie
  transaction.
- Balances, statistics, and receipt provisional totals are computed locally
  from local tables using JavaScript mirrors of the Python domain functions.
- The server remains authoritative for validation, canonical IDs, timestamps,
  activity logging, recurrence materialization, and AI.
- Guest mode preserves capability-URL behavior: anyone with the group link
  can read and write. This is not per-group privacy.
- Admin operations and AI extraction are online-only.
- Offline image attachments are queued as blobs and uploaded after reconnect.
- Live currency-rate lookup is unavailable offline; the last cached rate and a
  manual override are available.

### 2.5 Synchronization protocol

Implement the server side in Stage 6 and the client side in Stage 9B.

#### Entity versioning

Every synchronizable row has:

- `id`: string; client-generated; legacy IDs preserved;
- `updated_at`: UTC, server-set;
- `version`: integer, incremented on every server write;
- `deleted_at`: nullable tombstone;
- `group_id`, where applicable.

#### Operation envelope

```json
{
  "op_id": "uuid",
  "group_id": "group-id",
  "entity_type": "expense",
  "entity_id": "expense-id",
  "op_type": "create | update | delete",
  "base_version": 3,
  "payload": { "validated entity fields only": "..." },
  "client_time": "2026-10-24T12:00:00Z"
}
```

#### Push

`POST /api/sync/push` accepts at most 50 operations. Each operation is applied
in a transaction, appended to `sync_changes`, and answered independently.

```json
{
  "results": [
    {
      "op_id": "…",
      "status": "applied",
      "entity": {},
      "version": 4,
      "seq": 123
    },
    {
      "op_id": "…",
      "status": "conflict",
      "server_entity": {},
      "version": 5
    },
    {
      "op_id": "…",
      "status": "error",
      "code": "validation_error",
      "detail": "…"
    }
  ],
  "cursor": 123
}
```

#### Pull

`POST /api/sync/pull` accepts:

```json
{
  "cursor": 100,
  "group_ids": ["…"],
  "limit": 500
}
```

It returns full snapshots, never diffs:

```json
{
  "changes": [],
  "cursor": 123,
  "has_more": false
}
```

#### Bootstrap

`GET /api/sync/bootstrap?group_id=…` returns the full group snapshot and the
current cursor. It is used for first synchronization and whenever a cursor is
older than the 30-day change-log retention.

#### Conflict rules

| Entity | Rule |
|---|---|
| Group metadata and participant name | Last writer wins; client retries only when explicitly safe |
| Star/archive membership | Last writer wins per user |
| Expense create | Idempotent by entity and operation ID; duplicate returns the existing row |
| Expense update/delete | Conflict queue; never silently lose a financial edit. UI offers "keep mine", "use server", and "duplicate as new" |
| Receipt item/portion edits | Last writer wins per item; portions are a versioned replace-set |
| Delete versus update | Tombstone wins; UI shows "deleted elsewhere" |

#### Idempotency and ordering

- `sync_operations(op_id PRIMARY KEY, user_id, applied_at, result_json)`
  retains results for 7 days. A replayed operation returns the stored result.
- The client sends operations FIFO per group.
- The client includes `base_version`; stale updates receive a conflict.
- Change-log rows use an autoincrementing sequence number.
- A bootstrap fallback is required when the requested cursor is too old.

### 2.6 Authentication and authorization

- Access token: JWT, 15-minute lifetime, held in memory in the SPA.
- Refresh token: opaque random value, hashed in the database, delivered in an
  `HttpOnly`, `Secure`, `SameSite=Lax` cookie scoped to `/api/auth`.
- `POST /api/auth/refresh` rotates the refresh token and returns a new access
  token. The API client retries one failed request after refreshing.
- OAuth state uses an `HttpOnly` cookie. `return_to` must be a relative,
  same-origin path.
- On application start, the client attempts to refresh the session. If the
  device is offline, local access continues and refresh is retried later.
- An expired access token does not block local reads or writes.
- `sync_users` is the default tier. `group_creators` and `admin` can create
  groups. Only `admin` can access admin endpoints.
- The access token contains `sub`. User tier is loaded from the database on
  every request so promotion or demotion takes effect immediately.
- Group endpoints remain unauthenticated to preserve shared links.
- Refresh and logout require CSRF protection appropriate to cookie auth.

### 2.7 API conventions

- All endpoints are under `/api` and use plural resource names.
- JSON uses `snake_case`.
- Lists use `{ items, total, limit, offset }`.
- Errors use `{ "detail": "…" }`; validation errors use FastAPI's 422 shape.
- Create returns 201, empty delete returns 204, and partial update uses PATCH.
- Money is integer minor units. Conversion rates are decimal strings.
- Timestamps are ISO 8601 UTC with `Z`. `expense_date` is `YYYY-MM-DD`.
- IDs are strings. New IDs are UUIDv4; legacy IDs are preserved.
- `/api/health`, `/api/health/liveness`, and `/api/health/readiness` remain
  available.
- The public URL scheme `/groups/:groupId/...` is preserved.

### 2.8 Non-goals for v1

- Per-group ACLs or private groups; the link is the capability.
- CRDTs or real-time collaborative editing.
- Offline AI extraction; queued until online.
- Native mobile applications.
- PostgreSQL; SQLite with WAL is the v1 database.
- Replacing every translation; port existing locale files.
- A conversational bill-splitting assistant beyond the existing receipt
  line-item calculator and category inference.
- Dual-running the old and new applications during cutover.

---

## 3. Stage map

| Stage | Outcome | Est. | Gate |
|---|---|---:|---|
| 0A | Reference source and baseline pre-flight | 0.5–1 d | Source present; baseline recorded |
| 0B | Inventory and parity matrix | 1–2 d | Every discovered feature mapped |
| 0C | ADRs and contracts | 1 d | User sign-off |
| 1 | Backend/frontend scaffold, CI, launcher | 1 d | Health, lint, test, build green |
| 2 | Schema, Alembic, legacy importer | 2–3 d | Import integrity and balances match |
| 3 | Python domain core and golden fixtures | 2–3 d | Fixture parity and property tests |
| 4 | Auth, tiers, OAuth, admin API | 2 d | Auth/RBAC matrix green |
| 5A | Groups and participants REST API | 1–2 d | Contract and parity tests green |
| 5B | Expenses, recurrence, documents API | 2 d | Contract and parity tests green |
| 5C | Balances, stats, activity, categories API | 1–2 d | Contract and parity tests green |
| 5D | Exports and OpenAPI contract | 1 d | Export parity and OpenAPI green |
| 6 | Server-side synchronization protocol | 2–3 d | Idempotency and conflict tests green |
| 7 | Receipts and AI smart-split API | 2–3 d | Mocked AI and receipt parity green |
| 8A | Repository-based SPA shell, auth, group list | 2–3 d | Online groups/auth e2e green |
| 8B | Group and expense UI | 3–4 d | Online expense e2e green |
| 8C | Balances and statistics UI | 2–3 d | Online stats e2e green |
| 8D | Receipts and admin UI | 2–3 d | Full online e2e green |
| 9A | Dexie repository read path | 2 d | Offline read and reload green |
| 9B | Outbox, push/pull, conflicts | 2–3 d | Offline write and sync green |
| 9C | Local calculations and localStorage migration | 1–2 d | Offline parity green |
| 10A | Workbox PWA, manifest, update UX | 1–2 d | Installability and offline boot green |
| 10B | Pending-sync UX, queued uploads, persistence | 1–2 d | Offline matrix green |
| 11 | Authenticated group sync and admin polish | 1–2 d | Two-device sync green |
| 12 | Deployment, performance, rollback | 2–3 d | Dry run and rollback drill green |
| 13 | Decommission Node application | 0.5 d | Old application archived |

Estimated total: approximately 32–43 focused development days.

---

## 4. Detailed stages

### Stage 0A — Reference source and baseline pre-flight

**Goal:** establish a verified behavioral oracle before writing a plan or code.

**Deliverables**

- Confirm `spliit/` contains the complete fork source, including all custom
  features and design documents.
- If the source is missing or partial, stop and ask the user to restore it.
- Run `npm ci` in `spliit/` and execute the existing Jest suite and as much of
  the Playwright suite as the environment permits.
- Record exact pass/fail/skip counts and environmental failures.
- Confirm the fixture databases and their expected contents.
- Mark every `[VERIFY]` item in §1 confirmed or corrected.
- Confirm the reference-file paths in §1.4.
- Write `docs/reference-baseline.md` with commands, counts, fixture inventory,
  and discrepancies.

**Verification**

- The source and both databases exist and are readable.
- The baseline report contains command output rather than estimates.
- Every `[VERIFY]` item has a confirmed or corrected value.

**Gate:** verified source and recorded baseline. No implementation work starts
without this gate.

---

### Stage 0B — Inventory and executable parity matrix

**Goal:** make completeness machine-verifiable.

**Deliverables**

- Create `docs/parity-matrix.yml` with one stable Feature ID per behavior.
- Each row includes:
  - feature ID and category;
  - reference source file and symbol or route;
  - target API endpoint and UI route;
  - implementing stage;
  - verification test or spec;
  - custom/standard classification;
  - offline capability classification.
- Include every page, tRPC procedure, Jest behavior test, and Playwright spec.
- No `TBD` cells.
- Create `scripts/check_parity_matrix.py` that:
  - discovers reference pages, router files, and e2e specs;
  - verifies each discovered behavior is represented;
  - verifies every matrix row names at least one test;
  - verifies every feature ID is unique;
  - exits nonzero on missing mappings.
- Create `docs/parity-report.md` as a generated view of the matrix.

**Example row**

```yaml
- id: EXP-SPLIT-AMOUNT
  category: standard
  reference: src/lib/api.ts::createExpense
  api: POST /api/groups/{group_id}/expenses
  ui: /groups/:groupId/expenses/create
  stage: 5B
  tests:
    - backend/tests/test_expenses_api.py::test_create_by_amount
    - frontend/e2e/split-modes.spec.ts
  offline: read-write
```

**Verification**

```bash
python scripts/check_parity_matrix.py
```

**Gate:** checker passes and user reviews all custom-feature rows.

---

### Stage 0C — Architecture decisions and contracts

**Goal:** remove ambiguity before implementation.

**Deliverables**

- `docs/adr/0001-stack.md`: selected stack and rationale.
- `docs/adr/0002-offline-sync.md`: protocol, conflicts, retention, idempotency.
- `docs/adr/0003-auth.md`: access/refresh tokens, OAuth, tiers, guest model.
- `docs/adr/0004-money-dates-ids.md`: integer money, decimal strings, UTC dates,
  preserved IDs, `snake_case`.
- `docs/repository-contract.md`: exact repository methods and semantics.
- `docs/api.md`: resource list and request/response examples.
- `docs/offline-capabilities.md`: online, offline, queued, and online-only
  feature matrix.
- `docs/runbook-cutover.md`: cutover and rollback outline.
- Resolve the decisions in §8.

**Gate:** ADRs, contracts, and open decisions are signed off.

---

### Stage 1 — Repository scaffold, tooling, CI

**Goal:** a running skeleton with both services and green checks.

**Backend deliverables**

- Exact-pinned `requirements.txt` and `requirements-dev.txt`.
- `app/main.py` containing only application creation, middleware, and router
  registration.
- `core/config.py`, `core/database.py`, `api/health.py`, and `api/deps.py`.
- Package initialization for all application layers.
- `alembic.ini` and `alembic/env.py` wired to `SQLModel.metadata`.
- Test fixtures using in-memory SQLite and `StaticPool`.
- `pytest.ini`, `ruff.toml`, coverage configuration, and `.env.example`.

**Frontend deliverables**

- Vite + React, plain `.jsx`.
- `services/config.js` and one private HTTP request implementation in
  `services/api.js`.
- `router.jsx`, `App.jsx`, and `main.jsx`.
- Tailwind 4 and shadcn-compatible CSS variables.
- Vitest + Testing Library + jsdom smoke test.
- `jsconfig.json` with `checkJs` and oxlint configuration.

**Root deliverables**

- `dev` launcher for both services against `data/dev/`.
- `Makefile` with `dev`, `test`, `lint`, `typecheck`, `e2e`, and `build`.
- CI for backend lint/format/test/coverage and frontend lint/typecheck/test/build.
- `.gitignore` for virtual environments, dependencies, data, and build output.

**Verification**

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
PYTHONPATH=. pytest -n auto
ruff check .
ruff format --check .

cd ../frontend
npm ci
npm test -- --run
npm run lint
npm run typecheck
npm run build

cd ..
./dev
curl -f http://localhost:5173/api/health
```

**Gate:** all commands green; the health endpoint returns 200 through the Vite
proxy.

**Do not:** add domain models, auth, Dexie, or PWA implementation.

---

### Stage 2 — SQLModel schema, Alembic, legacy importer

**Goal:** preserve every existing row and import a production database without
loss.

**Deliverables**

- One model file per table under `app/models/`:
  - core: `Group`, `Participant`, `Category`, `Expense`, `ExpensePaidFor`,
    `ExpenseDocument`, `Activity`, `RecurringExpenseLink`;
  - auth: `User`, `Account`, `RefreshToken`, `UserGroup`;
  - receipts: `Receipt`, `ReceiptItem`, `ReceiptItemPortion`, `ReceiptOptOut`;
  - sync: `SyncChange`, `SyncOperation`, `ImportRun`.
- Preserve Prisma field semantics while using:
  - UTC `datetime` for internal expense dates;
  - `Decimal` conversion rates serialized as strings;
  - integer minor units for money;
  - timezone-aware UTC timestamps;
  - `version` and `deleted_at` synchronization columns.
- Add required foreign keys, uniqueness constraints, composite primary keys,
  and performance indexes.
- Split Alembic migrations into:
  - `0001_core_schema`;
  - `0002_receipts_schema`;
  - `0003_sync_and_auth_schema`.
- `scripts/import_legacy_sqlite.py`:
  - opens the source read-only;
  - refuses a non-empty target unless `--reset` is supplied;
  - parses Prisma dates, booleans, and decimals exactly;
  - seeds missing default categories;
  - preserves IDs and timestamps;
  - imports all application tables except sessions and verification tokens;
  - preserves orphan documents and activities;
  - writes an `ImportRun` row with source checksum, counts, and duration;
  - is idempotent and refuses partial re-imports.
- `scripts/verify_import.py`:
  - compares table counts;
  - compares per-group participants, expenses, and amount sums;
  - checks `PRAGMA integrity_check` and `PRAGMA foreign_key_check`;
  - compares balances with a reference-generated golden fixture.
- Temporary `spliit/scripts/export-legacy-balances.ts` generates the golden
  balance fixture using the reference implementation.
- A small fixture database covers every table and the known edge cases.

**Verification**

```bash
cd backend
alembic upgrade head
alembic downgrade base && alembic upgrade head
PYTHONPATH=. pytest tests/test_import_legacy.py -n auto

cp ../spliit/spliit-data/spliit.db /tmp/spliit-copy.db
python scripts/import_legacy_sqlite.py --source /tmp/spliit-copy.db --target /tmp/new.db
python scripts/verify_import.py --old /tmp/spliit-copy.db --new /tmp/new.db
sqlite3 /tmp/new.db "PRAGMA foreign_key_check; PRAGMA integrity_check;"
```

**Expected:** zero missing rows, zero foreign-key violations, matching balances
for all groups, and `integrity_check` returning `ok`.

**Gate:** import and verification pass against every confirmed fixture database.

**Common failure modes:** truncating `expenseDate`; converting `Decimal` to
`float`; dropping orphan documents; importing sessions; or letting SQLite
silently coerce booleans.

---

### Stage 3 — Python domain core and golden fixtures

**Goal:** match every financial, date, and receipt calculation exactly.

**Deliverables**

- Pure modules under `app/utils/` with no I/O, database, or configuration
  dependencies:
  - `money.py`;
  - `shares.py`;
  - `balances.py`;
  - `totals.py`;
  - `receipt_split.py`;
  - `receipt_extraction.py`;
  - `currency.py`;
  - `recurrence.py`;
  - `dates.py`.
- Reproduce exact tie-breaking, negative-amount, monthly-clamp, and stable
  comparator behavior from the reference.
- Generate deterministic `shared/fixtures/domain/*.json` with a temporary
  reference script.
- Include edge cases for:
  - even splits;
  - one-third splits;
  - half splits;
  - two-of-three allocation;
  - repeated receipt items;
  - opt-outs;
  - negative amounts;
  - zero shares;
  - multi-currency;
  - monthly recurrence clamping;
  - reimbursements.
- `tests/test_domain_parity.py` asserts exact fixture equality.
- `tests/test_domain_properties.py` uses Hypothesis to check:
  - shares sum exactly to the expense amount;
  - receipt participant totals sum to the item total;
  - no negative zero or lost minor units.

**Verification**

```bash
cd backend
PYTHONPATH=. pytest tests/test_domain_parity.py tests/test_domain_properties.py -n auto
```

**Gate:** 100% fixture parity and green property tests. This is the primary
correctness gate of the migration.

---

### Stage 4 — Authentication, tiers, OAuth, admin API

**Goal:** preserve the account and tier model while improving session
security.

**Deliverables**

- `core/security.py`: JWT creation/verification, refresh-token generation and
  hashing, timing-safe comparisons.
- `core/oauth.py`: Google/GitHub authorization, token exchange, profile
  retrieval, state cookie, and account linking.
- `api/deps.py`: current/optional user and tier requirement dependencies.
- Authentication endpoints:
  - `GET /api/auth/me`;
  - `GET /api/auth/oauth/{provider}/start`;
  - `GET /api/auth/oauth/{provider}/callback`;
  - `POST /api/auth/refresh`;
  - `POST /api/auth/logout`.
- Admin endpoints for metrics, users, groups, tier changes, preauthorization,
  and deletion.
- Admin bootstrap CLI.
- Shared rate limiter for authentication endpoints.
- Tests for token tampering and expiry, refresh rotation and reuse detection,
  OAuth state mismatch, open redirect, tier matrix, admin authorization,
  bootstrap behavior, email linking, and provider discovery.

**Verification**

```bash
cd backend
PYTHONPATH=. pytest tests/test_auth.py tests/test_admin.py tests/test_rbac.py -n auto
python -m app.scripts.make_admin --email test@example.com --db /tmp/new.db
```

**Gate:** the tier matrix is enforced; no endpoint accepts an invalid token;
refresh rotation invalidates reuse of the old token.

---

### Stage 5A — Groups and participants REST API

**Deliverables**

- Thin group router and group service.
- Endpoints for group list, creation, retrieval, update, details, access
  recording, star, archive, membership removal, and legacy group merge.
- Participant CRUD and validation.
- Schemas for every request and response.
- HTTP parity fixtures and tests for each group and participant behavior.

**Verification**

```bash
cd backend
PYTHONPATH=. pytest tests/test_groups_api.py tests/test_group_sync.py -n auto
```

**Gate:** parity matrix rows for groups and participants have passing tests;
routers contain no model or SQL imports.

---

### Stage 5B — Expenses, recurrence, documents API

**Deliverables**

- Expense list with pagination and filters.
- Expense create, retrieve, update, and delete.
- Split-mode validation, currency conversion, and paid-for relationships.
- Idempotent, transactional recurrence materialization preserving the
  reference's monthly clamp and `next_expense_created_at` semantics.
- Document upload, retrieval, and deletion with size/type/path validation.
- Activity logging in the same transaction as the mutation.
- HTTP parity tests covering rounding, reimbursement, recurrence, and documents.

**Verification**

```bash
cd backend
PYTHONPATH=. pytest tests/test_expenses_api.py tests/test_recurrence.py -n auto
```

**Gate:** every expense matrix row has a passing parity test.

---

### Stage 5C — Balances, statistics, activity, categories API

**Deliverables**

- Public and personal balances.
- Suggested reimbursements with the reference comparator.
- Group and personal totals, category and month breakdowns, participant
  totals, spending over time, recurring summaries, date filters, and
  drill-downs.
- Activity and category endpoints.
- HTTP parity tests for all statistics and balance behaviors.

**Verification**

```bash
cd backend
PYTHONPATH=. pytest tests/test_balances_api.py tests/test_stats_api.py \
  tests/test_activities_api.py -n auto
```

**Gate:** all corresponding matrix rows pass.

---

### Stage 5D — Exports and OpenAPI contract

**Deliverables**

- CSV and JSON exporters.
- Preserve columns, split-mode labels, decimal formatting, participant sign
  convention, and formula-injection escaping.
- Runtime feature endpoint.
- OpenAPI snapshot and lint validation.
- A check that every API route has request/response schemas where applicable.

**Verification**

```bash
cd backend
PYTHONPATH=. pytest tests/test_exports.py tests/test_openapi.py -n auto
ruff check . && ruff format --check .
```

**Gate:** export fixtures match; OpenAPI snapshot is reviewed and stable.

---

### Stage 6 — Server-side synchronization protocol

**Goal:** accept offline edits idempotently and serve a reliable change feed.

**Deliverables**

- `api/sync.py`: bootstrap, pull, and push endpoints.
- `services/sync.py`:
  - explicit entity and field whitelists;
  - per-entity apply functions;
  - transaction per operation;
  - change-log append and version increment;
  - idempotency table;
  - stale-version conflict detection;
  - tombstones;
  - group claim/merge;
  - cursor validation and bootstrap fallback;
  - change-log compaction.
- Tests for:
  - replayed operations applying once;
  - stale versions returning a conflict;
  - duplicate creates being idempotent;
  - tombstones surviving pull;
  - pagination and `has_more`;
  - expired cursors requiring bootstrap;
  - cross-group operations being rejected;
  - unknown entities and fields being rejected;
  - concurrent pushes not duplicating recurrence frames;
  - rollback when one operation in a request fails according to the agreed
    per-operation transaction policy.

**Verification**

```bash
cd backend
PYTHONPATH=. pytest tests/test_sync.py tests/test_sync_conflicts.py -n auto
```

**Gate:** synchronization suite green; a scripted two-client create/update/delete
and replay scenario converges to identical server state.

---

### Stage 7 — Receipts and AI smart-split API

**Goal:** preserve receipt scanning, item allocation, and category inference.

**Deliverables**

- Storage abstraction with local-disk default and S3-compatible adapter.
- Upload endpoint with size/type limits, traversal protection, and an SSRF
  allowlist for URLs sent to AI.
- OpenAI-compatible AI service using `AI_*` precedence over `OPENAI_*`.
- Ported prompts and strict JSON schemas.
- Defensive parsing: malformed output becomes `FAILED`, never a crash.
- Endpoints for total extraction, item/charge extraction, receipt retrieval,
  item CRUD, portion replacement, opt-outs, apply-to-expense, receipt link,
  and category inference.
- Server recomputation of provisional totals; client totals are never trusted.
- Atomic one-call-per-image claim with stale-claim recovery.
- Server-enforced feature flags exposed through `/api/features`.
- Rate limits and limits for items, portions, names, and amounts.
- Mocked tests for flags, malformed output, unassigned/shared items, adjustment
  synthesis, concurrent claims, fractional splitting, opt-outs, and apply
  invariants.

**Verification**

```bash
cd backend
PYTHONPATH=. pytest tests/test_receipts.py tests/test_ai.py \
  tests/test_receipt_apply.py -n auto
```

**Gate:** all tests pass with zero real AI network calls; the sample receipt's
provisional totals match the reference fixture.

---

### Stage 8A — Repository-based SPA shell, auth, group list

**Goal:** a working SPA whose hooks and components use only the repository
contract.

**Deliverables**

- `repository/contract.js` and `repository/online.js` implement the documented
  repository interface.
- Hooks and components never import `services/api.js` directly.
- Routes:
  - `/` redirects to `/groups`;
  - `/groups`;
  - `/groups/create`;
  - `/groups/:groupId` redirects to expenses;
  - group expenses, balances, statistics, activity, information, and edit
    routes;
  - `/admin`.
- Header, locale switcher, theme toggle, user menu, and toasts.
- Login dialog with Google/GitHub, tier-aware group creation, and approval
  messaging.
- Group list for recent, starred, and archived groups; add by URL; remove;
  global balance.
- Port existing locale files and enforce key parity across locales.
- Loading, error, and empty states; accessible labels.
- Port e2e seeding helpers and preserve existing user-visible selectors and
  assertions where practical.
- Playwright configuration with a `BASE_URL` override.

**Verification**

```bash
cd frontend
npm test -- --run
npm run lint && npm run typecheck && npm run build
cd .. && ./dev
npx playwright test e2e/group-management.spec.ts \
  e2e/global-balance.spec.ts --grep "Recent groups|global"
```

**Gate:** groups and authentication work online, deep links load directly, and
an automated architecture check proves no hook or component imports `api.js`.

---

### Stage 8B — Group and expense UI

**Deliverables**

- Group header, tabs, information/edit pages, and participant management.
- Active-user modal and per-group active-user persistence.
- Expense list with search, filters, pagination, date groups, category icons,
  reimbursement display, and document counts.
- Expense create/edit/delete form with all split modes, paid-by/paid-for,
  multi-currency, recurrence, documents, and saved splitting defaults.
- Activity list and export buttons.
- All hooks use the repository contract.
- Port domain utilities needed by forms and run shared fixture tests in
  Vitest.
- Port zod validation schemas.

**Verification**

```bash
cd frontend
npm test -- --run
npx playwright test e2e/core.spec.ts e2e/expense-edit-delete.spec.ts \
  e2e/expense-variants.spec.ts e2e/split-modes.spec.ts \
  e2e/multi-currency.spec.ts e2e/recurrence.spec.ts
```

**Gate:** all listed specs pass and UI balances match the API for every split
mode.

---

### Stage 8C — Balances and statistics UI

**Deliverables**

- Public balances and suggested reimbursements.
- "Mark as paid" reimbursement flow and multi-currency repayment.
- Statistics page with totals, personal totals, time series, participant and
  category breakdowns, recurring spending, range selection, and drill-downs.
- Repository-backed balance and statistics hooks.
- Locale keys for all new screens in all locales.

**Verification**

```bash
cd frontend
npm test -- --run
npx playwright test e2e/global-balance.spec.ts e2e/reimbursements.spec.ts \
  e2e/repayment-currency.spec.ts e2e/stats.spec.ts \
  e2e/stats-breakdown.spec.ts e2e/active-user.spec.ts
```

**Gate:** all listed specs pass.

---

### Stage 8D — Receipts and admin UI

**Deliverables**

- Receipt upload/compression and total extraction.
- Items UI with unassigned/shared/per-participant sections.
- Fractional assignment, item movement/removal, opt-outs, item CRUD,
  provisional totals, reconciliation, divergence note, and apply-to-expense.
- Admin metrics, users, groups, tier changes, deletion, and preauthorization.
- Repository-backed receipt and admin hooks.
- Online-only messaging when AI is unavailable.

**Verification**

```bash
cd frontend
npm test -- --run
npx playwright test e2e/receipts.spec.ts e2e/admin.spec.ts
```

**Gate:** full online Playwright suite is green, except PWA specs reserved for
Stage 10. **M1 is shippable here.**

---

### Stage 9A — Dexie repository read path

**Goal:** every screen reads from IndexedDB without changing hooks or
components.

**Deliverables**

- `services/db.js` with groups, participants, expenses, paid-for rows,
  documents, activities, receipts, receipt items/portions/opt-outs,
  categories, user groups, outbox, sync state, conflicts, blobs, and metadata.
- Indexes for `group_id`, `updated_at`, `version`, and `deleted_at`.
- `repository/local.js` implements the same contract as `repository/online.js`.
- Repository selection changes only at the interface boundary.
- First load bootstraps the group list and lazily bootstraps full group data;
  recently visited groups are prefetched.
- Tests use fake-indexeddb and seeded repositories rather than mocked `fetch`.

**Verification**

```bash
cd frontend
npm test -- --run
npx playwright test e2e/core.spec.ts e2e/group-management.spec.ts
```

**Gate:** after stopping the API, reloading a previously opened group shows
cached data. An automated check proves the local repository satisfies the
documented contract.

---

### Stage 9B — Outbox, push/pull, conflicts

**Goal:** make offline writes durable, idempotent, and convergent.

**Deliverables**

- `services/outbox.js`: enqueue, FIFO per group, retry/backoff, batches of 50,
  status, attempt count, and last error.
- Repository writes update Dexie and enqueue in one transaction, marking
  records pending.
- `services/sync.js`:
  - single-flight synchronization on start, online, visibility, debounced
    after mutation, and every 60 seconds online;
  - push then pull;
  - cursor per guest or user scope;
  - changes applied in one transaction;
  - tombstone handling;
  - conflict queue and resolution operations;
  - bootstrap fallback;
  - `navigator.locks` and `BroadcastChannel` leader election across tabs.
- Sync status hook and UI: pending badges, banner, and conflict dialog.
- Offline group creation is allowed only from a cached permitted tier. The
  server revalidates the tier when the operation is pushed.
- New Playwright scenario covers:
  1. load online, go offline, reload, and see data;
  2. create/edit/delete offline, reload, reconnect, and synchronize exactly
     once;
  3. two contexts with divergent edits and eventual conflict resolution;
  4. explicit conflict resolution paths;
  5. lost push response and retry without duplication;
  6. guest group login and merge.

**Verification**

```bash
cd frontend
npm test -- --run
npx playwright test e2e/offline-sync.spec.ts
```

**Gate:** offline synchronization suite green with no duplicates after forced
retries.

---

### Stage 9C — Local calculations and localStorage migration

**Goal:** make balances, statistics, and receipt splitting work offline and
match the server.

**Deliverables**

- JavaScript mirrors of shares, balances, totals, receipt splitting, currency,
  recurrence, and date utilities.
- Vitest tests replay the same golden domain fixtures used by Python.
- Local hooks calculate from Dexie tables.
- The server remains authoritative for recurrence. Offline clients show
  materialized frames; newly created recurring expenses receive future frames
  after synchronization.
- One-time migration into Dexie metadata, guarded by
  `migrated_from_localstorage`, for:
  - `recentGroups`;
  - `starredGroups`;
  - `archivedGroups`;
  - `${groupId}-activeUser`;
  - `${groupId}-newUser`;
  - `newGroup-activeUser`;
  - `${groupId}-defaultSplittingOptions`.
- User-triggered, versioned JSON backup and restore, including pending blobs
  when feasible.

**Verification**

```bash
cd frontend
npm test -- --run
npx playwright test e2e/offline-sync.spec.ts e2e/stats.spec.ts \
  e2e/global-balance.spec.ts e2e/reimbursements.spec.ts \
  e2e/active-user.spec.ts
```

**Gate:** JavaScript fixtures match Python 100%; offline balances and statistics
match the server after synchronization; old localStorage data appears after
upgrade.

---

### Stage 10A — Workbox PWA, manifest, update UX

**Goal:** an installable application that boots offline with the complete UI.

**Deliverables**

- `vite-plugin-pwa` with:
  - precached HTML, JavaScript, CSS, fonts, icons, and manifest;
  - `navigateFallback: '/index.html'`;
  - image and font runtime caching;
  - `/api` explicitly `NetworkOnly`;
  - versioned caches and outdated-cache cleanup.
- Update prompt with an explicit reload action. Do not automatically
  `skipWaiting`.
- Manifest with name, short name, `/groups` start URL, standalone display,
  theme/background colors, 192/512/maskable icons, and shortcuts.
- Apple touch icon and splash behavior.
- Offline fallback for unknown routes.
- PWA hook for install prompt, update state, and standalone detection.
- Dexie schema migration compatibility is tested before an update activates.
- Tests for installability, cache contents, offline boot, and update flow.

**Verification**

```bash
cd frontend
npm run build
npx serve -s dist -l 4173
npx playwright test e2e/pwa.spec.ts e2e/pwa-offline.spec.ts
npx lighthouse http://localhost:4173 --only-categories=pwa --chrome-flags="--headless"
```

**Gate:** the app installs, boots offline with cached data, never stores `/api`
responses in Workbox caches, and pending outbox data survives updates.

---

### Stage 10B — Pending-sync UX, queued uploads, persistence

**Goal:** make offline behavior clear and reliable.

**Deliverables**

- Global status banner: offline, syncing, pending count, error, and retry.
- Per-entity pending markers.
- Background Sync is optional where supported. Startup, `online`, visibility,
  mutation, and manual retry are the required reliable paths.
- `navigator.storage.persist()`, quota display, low-quota warning, and backup.
- Offline image attachments queue blobs, upload after reconnect, then run AI
  extraction with a "scan pending" state.
- AI controls are disabled offline with an explanation; manual expense entry
  remains available.
- Tests cover queued operations surviving reload, browser background-sync
  fallback, storage warning, and queued uploads.

**Verification**

```bash
cd frontend
npm test -- --run
npx playwright test e2e/offline-sync.spec.ts e2e/pwa-offline.spec.ts
```

**Gate:** the complete offline test matrix is green, no writes are lost, and
status is understandable. **M2 is shippable here.**

---

### Stage 11 — Authenticated group sync and admin polish

**Goal:** make login-based group synchronization work end-to-end.

**Deliverables**

- On login, merge local group IDs into `UserGroup`, queue the merge if offline,
  bootstrap the user scope, and pull all groups without duplicating the guest
  cache.
- Synchronize star/archive state as last-writer-wins per user.
- Remove groups from the synchronized list without deleting their data.
- Record group access after a visit, debounced.
- Global balance uses the active user and cached expenses.
- Polish the admin dashboard.
- Two-device tests cover:
  - create on A, visible on B;
  - star on A, visible on B;
  - guest group claimed on login without duplication;
  - offline login merge followed by reconnect.

**Verification**

```bash
cd frontend
npx playwright test e2e/group-sync.spec.ts e2e/admin.spec.ts
cd ../backend
PYTHONPATH=. pytest tests/test_admin.py tests/test_groups_sync.py
```

**Gate:** two-context synchronization suite green and tier changes take effect
on the next request.

---

### Stage 12 — Deployment, performance, rollback

**Goal:** deploy safely without losing data or losing a tested rollback path.

**Deliverables**

- `compose.yaml`:
  - `api`: Python 3.12 slim, Uvicorn, SQLite WAL, persistent volume,
    readiness health check;
  - `web`: nginx serving the built SPA, SPA fallback, `/api` proxy, compression,
    and hashed-asset caching;
  - optional backup service.
- `Dockerfile.api`, `Dockerfile.web`, and `.dockerignore`.
- Complete `.env.example`.
- SQLite `WAL`, `busy_timeout`, `foreign_keys=ON`, and short transactions.
- Backup and restore scripts using SQLite backup and upload archives.
- Structured logs, request IDs, optional Sentry.
- Finalize `docs/runbook-cutover.md` with:
  1. staging dry run on a production copy;
  2. maintenance announcement;
  3. stop old application;
  4. back up database and uploads;
  5. import and verify;
  6. start and smoke-test the new stack;
  7. switch reverse proxy;
  8. monitor 30–60 minutes;
  9. rollback proxy and restore backup if needed;
  10. keep the old stack stopped for 7 days.
- Security checklist:
  - HTTPS;
  - secure cookies;
  - CORS allowlist;
  - CSRF protection;
  - rate limits;
  - upload limits;
  - SSRF protection;
  - server-only AI keys;
  - admin bootstrap;
  - dependency audits;
  - no secrets in logs.
- Performance targets:
  - first expense page p95 below 300 ms with 10,000 expenses;
  - 50-operation sync push below 500 ms;
  - bootstrap of a 1,000-expense group below 1 second;
  - initial JavaScript below 300 KB gzip with route-level splitting;
  - offline boot below 2 seconds on a mid-range phone;
  - Lighthouse PWA installable.

**Verification**

```bash
python backend/scripts/import_legacy_sqlite.py --source prod-copy.db --target new.db
python backend/scripts/verify_import.py --old prod-copy.db --new new.db
docker compose build && docker compose up -d
curl -f http://localhost:8080/api/health/readiness
npx playwright test
```

Also run a rollback drill and record recovery time.

**Gate:** production dry run, full e2e suite, performance targets, and rollback
drill pass with user sign-off.

---

### Stage 13 — Decommission Node application

**Deliverables**

- Archive `spliit/` on a tag or branch for reference.
- Remove old Docker, Compose, and CI files.
- Update the root README with architecture, development, deployment, backups,
  AI configuration, and offline behavior.
- Retain the importer and fixtures.

**Gate:** the new stack is the only documented path, and old data is backed up
and restorable.

---

## 5. Cross-cutting verification

### 5.1 Three-layer parity harness

1. **Domain fixtures:** exact outputs of the reference TypeScript pure
   functions. Python tests consume them in Stage 3; JavaScript tests consume
   them in Stage 9C.
2. **HTTP fixtures:** normalized responses from the reference data layer.
   Backend HTTP parity tests consume them in Stages 5A–5D.
3. **Playwright e2e:** the reference browser suite is the user-visible
   contract. Port it with minimal selector changes and add explicit offline,
   group-sync, PWA-offline, and admin scenarios.

Normalization rules:

- Sort arrays where the reference has no stable order.
- Remove server-generated timestamps and IDs only where documented.
- Keep money, shares, balances, categories, split modes, recurrence results,
  and export text exact.

### 5.2 E2E mapping

| Spec | Stage |
|---|---|
| `core.spec.ts` | 8B |
| `expense-edit-delete.spec.ts` | 8B |
| `expense-variants.spec.ts` | 8B |
| `split-modes.spec.ts` | 8B |
| `multi-currency.spec.ts` | 8B |
| `recurrence.spec.ts` | 8B |
| `group-management.spec.ts` | 8A/8B |
| `active-user.spec.ts` | 8C/9C |
| `global-balance.spec.ts` | 8A/8C/11 |
| `reimbursements.spec.ts` | 8C/11 |
| `repayment-currency.spec.ts` | 8C |
| `stats.spec.ts` | 8C |
| `stats-breakdown.spec.ts` | 8C |
| `pwa.spec.ts` | 10A/10B |
| New `pwa-offline.spec.ts` | 10A/10B |
| New `offline-sync.spec.ts` | 9B/10B |
| New `group-sync.spec.ts` | 11 |
| New `admin.spec.ts` | 11 |

All 14 reference specs and the 4 new specs must pass before cutover.

### 5.3 Offline test matrix

| Scenario | Expected |
|---|---|
| First visit online, then offline reload | Group, expenses, balances, and statistics are visible |
| Create expense offline | Appears immediately with pending marker |
| Edit/delete offline | Local state updates and operation is queued |
| Reload while offline | Pending writes persist |
| Reconnect | Push then pull; server state matches; no duplicates |
| Two devices, same group | Converge; metadata uses LWW; expense conflicts are queued |
| Lost response after push | Retry is idempotent |
| Guest creates group, then logs in | Group appears in the synchronized list without duplication |
| Offline image attachment | Blob queues; extraction occurs after reconnect |
| AI offline | Extraction is disabled with an explanation; manual entry works |
| Cache inspection | No `/api` responses in Workbox caches |
| Update available | Prompt appears; pending data survives reload |
| Long offline period | Local access continues; refresh and synchronization resume online |

### 5.4 Offline capability matrix

The final UI and documentation must use this classification.

| Capability | Online | Offline after sync | Queued for later |
|---|---:|---:|---:|
| Read group and expense data | Yes | Yes | — |
| Create/edit/delete expenses and participants | Yes | Yes | Yes |
| Balances and statistics | Yes | Yes | — |
| CSV/JSON export | Yes | Yes, from local data | — |
| Star/archive and active-user preferences | Yes | Yes | Yes |
| AI receipt extraction and category inference | Yes | No | Yes, after upload |
| Admin operations | Yes | No | No |
| Live currency-rate lookup | Yes | Cached/manual override | — |
| Authentication refresh | Yes | Deferred | — |

### 5.5 Automated architecture checks

Create `scripts/check_architecture.py` and equivalent frontend lint rules to
enforce:

- API routers do not import SQLAlchemy models or access the database session
  directly.
- Pure utility modules do not import HTTP, database, storage, or configuration
  modules.
- Hooks and components do not import `services/api.js`.
- Repository implementations satisfy the same documented contract.
- Every API endpoint defines appropriate schemas.
- Every parity-matrix row names at least one test.
- Every locale has the same key set as `en-US.json`.
- All required e2e specs exist.

### 5.6 Security checklist

- JWT secret is required in production; boot fails with the development
  default.
- Refresh tokens rotate, reuse is detected, and logout revokes them.
- OAuth state and `return_to` are validated; redirects cannot leave the origin.
- Cookies are `HttpOnly`, `Secure`, `SameSite=Lax`, and path-scoped.
- CSRF protection covers cookie-authenticated mutations.
- Access tokens are bearer tokens for mutations.
- Rate limits cover authentication, AI, uploads, and synchronization pushes.
- Upload size and type limits exist; path traversal is prevented.
- URLs sent to AI use an SSRF allowlist.
- CSV output escapes formula injection.
- React escapes user text; no `dangerouslySetInnerHTML`.
- Admin bootstrap is documented; there is no default admin.
- Dependency audits run in CI.
- The capability-URL model is documented without claiming privacy.

### 5.7 Risk register

| Risk | Impact | Mitigation | Stage |
|---|---|---|---|
| Reference inventory is incorrect | High | Blocking Stage 0A/0B verification | 0A–0C |
| Offline conflict loses financial data | High | Conflict queue; no silent LWW for expenses | 6, 9B |
| Python/JavaScript domain drift | High | Shared golden fixtures; property tests | 3, 9C |
| Prisma SQLite import quirks | High | Edge-case fixtures; checksums; production-copy dry run | 2, 12 |
| Service worker serves stale code | Medium | Versioned caches; update prompt; no automatic skip | 10A |
| Token expires offline | Medium | Local access continues; refresh on reconnect | 9B |
| AI cost or abuse | Medium | Flags, rate limits, atomic claim, SSRF protection | 7 |
| IndexedDB eviction or quota | Medium | Persistent storage, quota UI, versioned backup | 9C, 10B |
| SQLite contention | Medium | WAL, busy timeout, one worker, short transactions | 12 |
| OAuth callback behind proxy | Medium | `BASE_URL`, allowed origins, state cookie | 4, 12 |
| Locale regressions | Low | Automated key-parity check | 8A |
| Shared links break | High | Preserve IDs and routes; deep-link e2e tests | 8A |
| Recurrence duplicates across devices | Medium | Server-authoritative, idempotent materialization | 5B, 6 |
| Guest security misunderstood | Medium | Document capability model honestly | 0C, 12 |
| Repository boundary erodes | Medium | Automated import-boundary checks | 8A–10C |

---

## 6. Definition of done

- [ ] Stage 0A baseline and inventory are verified.
- [ ] Every parity-matrix row has a passing test and the matrix checker passes.
- [ ] Legacy import verifies counts, sums, balances, and foreign-key integrity on
      a production copy.
- [ ] Domain fixtures match 100% in Python and JavaScript.
- [ ] All 14 reference Playwright specs and 4 new specs pass.
- [ ] Offline suite passes: read, write, reload, reconnect, conflict,
      idempotency, guest-to-login merge, and queued upload.
- [ ] PWA installs, boots offline, preserves pending data through updates, and
      never caches `/api` responses.
- [ ] Auth/RBAC matrix passes; production refuses development secrets.
- [ ] Architecture checks and security checklist pass.
- [ ] Performance targets are met.
- [ ] Cutover runbook and rollback drill pass.
- [ ] User sign-off is recorded.

---

## 7. Flash-model prompt template

Use this template for each stage:

```text
Implement Stage <N> of /workspace/MIGRATION_PLAN.md only.

Read first:
- /workspace/MIGRATION_PLAN.md §<stage>
- <reference files listed in the stage>

Deliverables:
- <copy the stage's deliverable list>

Constraints:
- Follow the stack and repository conventions in plan §2.
- Do not modify /workspace/spliit/ except for temporary fixture scripts
  explicitly listed for this stage.
- Do not add libraries outside plan §2.1.
- Do not implement later stages.
- Do not weaken or skip a gate.

Verification:
- Run exactly: <commands from the stage>
- Report the command output and any deviations.

Stop when the gate passes. Do not start Stage <N+1>.
```

---

## 8. Decisions to resolve in Stage 0C

The bold values are the recommended defaults.

1. **Frontend language:** **plain `.jsx`** with `checkJs`, or TypeScript. The
   reference is TypeScript; plain JSX follows the starter convention but
   provides weaker compile-time guarantees. Decide before Stage 1.
2. **Offline conflict policy:** **queue expense conflicts for user choice**;
   use LWW only for metadata. Automatic LWW everywhere is simpler but risks
   losing financial edits.
3. **Authentication transport:** **HttpOnly refresh cookie plus an in-memory
   access token**. Persisting a bearer token in IndexedDB is simpler but less
   secure.
4. **Document storage:** **local disk by default plus an S3 adapter**.
5. **Smart-split scope:** **port the existing receipt line-item calculator and
   category inference**. A conversational assistant is a new feature.
6. **Cutover:** **a short maintenance window**. Dual-running requires a
   bidirectional bridge and is outside this plan.
7. **Database:** **SQLite in v1**, while keeping SQLModel portable for a later
   PostgreSQL migration.
8. **Offline scope is not open:** full editing of group data is the goal;
   administration and AI remain online-only.
