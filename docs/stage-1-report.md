# Stage 1 report — scaffold, tooling, CI

Date: 2026-10-24
Stage: 1

## Files added

### Backend

- `backend/requirements.txt`, `backend/requirements-dev.txt` (exact pins)
- `backend/app/main.py` (app factory, CORS, router registration only)
- `backend/app/core/config.py`, `backend/app/core/database.py`
- `backend/app/api/health.py`, `backend/app/api/deps.py`
- `backend/app/schemas/health.py`
- `backend/app/{api,models,schemas,services,storage,formats,core,utils,scripts}/__init__.py`
- `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`,
  `backend/alembic/versions/.gitkeep`
- `backend/tests/conftest.py`, `test_health.py`, `test_config.py`, `test_database.py`
- `backend/pytest.ini`, `backend/ruff.toml`, `backend/.env.example`

### Frontend

- `frontend/package.json`, `frontend/package-lock.json`, `frontend/jsconfig.json`
- `frontend/vite.config.js`, `frontend/index.html`, `frontend/.oxlintrc.json`
- `frontend/src/main.jsx`, `App.jsx`, `router.jsx`
- `frontend/src/services/config.js`, `services/api.js` (single fetch client)
- `frontend/src/components/common/PagePlaceholder.jsx`,
  `components/system/HealthIndicator.jsx`
- `frontend/src/styles/index.css` (Tailwind 4 + shadcn-compatible variables)
- `frontend/src/vite-env.d.ts`, `src/test/setup.js`
- `frontend/src/App.test.jsx`, `src/services/api.test.js`

### Root

- `dev` (executable launcher for API + Vite against `data/dev/`)
- `Makefile` (`install`, `dev`, `test`, `lint`, `typecheck`, `e2e`, `build`,
  `parity`, `clean`)
- `.github/workflows/ci.yml` (backend lint/format/test/coverage/audit,
  frontend lint/typecheck/test/build/audit, parity check)
- `.gitignore`
- `.env.example`

## Verification commands and output

### Backend

```bash
$ cd backend
$ DATABASE_URL=sqlite:////tmp/…/verify.db .venv/bin/alembic upgrade head
INFO  [alembic.runtime.migration] Context impl SQLiteImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.

$ PYTHONPATH=. .venv/bin/pytest -n auto
18 passed, 25 warnings in 3.21s
TOTAL 115 statements, 2 missed, 98.26% coverage
Required test coverage of 80% reached.

$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
22 files already formatted
```

`alembic downgrade base && alembic upgrade head` was also exercised manually
(exit 0 both ways) before the final run. Warnings are a Starlette notice about
`httpx` vs `httpx2` in `TestClient`; they do not affect results.

### Frontend

```bash
$ cd frontend
$ npm ci --no-audit --no-fund
added 124 packages in 937ms

$ npm test -- --run
Test Files  2 passed (2)
Tests       9 passed (9)

$ npm run lint
Found 0 warnings and 0 errors.

$ npm run typecheck
(no output; exit 0)

$ npm run build
✓ 28 modules transformed.
dist/index.html                   0.47 kB │ gzip:  0.29 kB
dist/assets/index-*.css           8.96 kB │ gzip:  2.77 kB
dist/assets/index-*.js          263.58 kB │ gzip: 83.71 kB
✓ built in 119ms
```

### Launcher and proxy

Port 8000 was occupied by an unrelated pre-existing service in this sandbox
(`server: uvicorn`, `{"status":"ok"}` without our version field). The launcher
detects this for its **default** port, picks the next free API port, and keeps
the required web port 5173:

```bash
$ ./dev
Port 8000 is busy; using API port 8001.
API:  http://127.0.0.1:8001/api/health
Web:  http://127.0.0.1:5173
Data: /workspace/data/dev

$ curl -fsS http://127.0.0.1:5173/api/health
{"status":"ok","version":"0.1.0"}          # HTTP 200 through the Vite proxy
$ curl -fsS http://127.0.0.1:5173/api/health/readiness
{"status":"ready","checks":{"database":"ok"}}   # HTTP 200
$ curl -fsS http://127.0.0.1:5173/api/health/liveness
{"status":"alive"}                         # HTTP 200
```

An explicitly supplied `API_PORT` is never overridden: if it is busy, the
launcher fails with a clear message. On a host where 8000 is free, the launcher
uses 8000 unchanged. Vite proxies `/api` to the selected API port in all cases.

### Audits and parity

```bash
$ backend/.venv/bin/pip-audit -r backend/requirements.txt
No known vulnerabilities found

$ cd frontend && npm audit --audit-level=high
found 0 vulnerabilities

$ backend/.venv/bin/python scripts/check_parity_matrix.py
OK: 111 features; 14 pages, 28 procedure files, 30 Jest suites, 14 Playwright specs all mapped.
```

## Gate checklist

- [x] Exact-pinned backend dependencies install cleanly.
- [x] `app/main.py` contains only creation, middleware and router registration.
- [x] Config, database engine/session and health endpoints exist.
- [x] Package initializers exist for every application layer.
- [x] Alembic is wired to `SQLModel.metadata`; upgrade/downgrade are clean.
- [x] Test fixtures use in-memory SQLite and `StaticPool`.
- [x] Pytest, coverage (98.26%), Ruff lint and Ruff format pass.
- [x] `.env.example` documents current variables and reserves later ones.
- [x] Vite + React (plain `.jsx`) builds; Tailwind 4 and shadcn tokens present.
- [x] One private HTTP implementation in `services/api.js`; one config module.
- [x] Router, App and entry point exist; routes preserve the reference URL
      scheme.
- [x] Vitest + Testing Library + jsdom smoke tests pass (9 tests).
- [x] `jsconfig.json` has `checkJs`; `tsc -p jsconfig.json` passes.
- [x] oxlint passes with zero warnings.
- [x] Root `dev`, `Makefile` and CI exist.
- [x] Health returns 200 through the Vite proxy.
- [x] No domain models, auth, Dexie or PWA code was added.

**Gate: PASSED.** The only deviation is the sandbox's occupied port 8000; the
health endpoint was verified through the required Vite proxy on port 5173.

## Deviations and open questions

1. **Port 8000 conflict.** An unrelated Uvicorn service already listens on
   `127.0.0.1:8000` in this sandbox. `./dev` now falls forward to the next free
   port for its default only, and the exact command was verified end to end.
   A clean host still uses 8000. An explicit `API_PORT` is never overridden.
2. **Alembic has no revisions yet.** Stage 1 deliberately ships an empty
   versions directory; `upgrade head` is a no-op until Stage 2 adds
   `0001_core_schema`.
3. **Coverage warning.** Pytest-xdist emits a harmless "No data was collected"
   warning from an early worker; combined coverage is still 98.26% and the
   threshold passes.
4. **Placeholder routes.** Group/expense/admin paths exist but render scaffold
   text. They are replaced in Stages 8A–8D; no domain behavior is implemented
   early.
5. **Auto-port selection is not implemented.** `./dev` fails loudly if a port is
   taken, which is intentional for a deterministic development launcher.

## Intentionally deferred

- SQLModel tables, constraints and Alembic `0001`–`0003` (Stage 2).
- Domain utilities, golden fixtures and property tests (Stage 3).
- Auth, OAuth, refresh rotation, tiers and admin API (Stage 4).
- Groups, expenses, balances, stats, exports and OpenAPI snapshot
  (Stages 5A–5D).
- Sync protocol (Stage 6), receipts/AI (Stage 7).
- Repository interface and SPA features (Stage 8A–8D).
- Dexie, outbox, local math, PWA, deployment/cutover (Stages 9–13).
