# Stage 12 report — Deployment, performance, rollback

Status: implementation complete; local verification green. The container build,
Compose startup and proxy-switch rehearsal are **blocked by the development
sandbox**, which has no Docker/Podman daemon or binary. They were replaced with
a production-shaped local API run and a data-path rollback rehearsal, and remain
required on staging before sign-off.

## 1. Outcome

The repository now has a production-shaped deployment:

- `Dockerfile.api` builds a Python 3.12 slim image, runs as UID 10001, applies
  Alembic migrations, and starts exactly one Uvicorn worker with proxy headers
  disabled.
- `Dockerfile.web` builds the Vite SPA and serves it from nginx.
- `frontend/nginx.conf` provides SPA deep-link fallback, `/api` proxying,
  compression, hashed-asset caching, no-store API responses, and no-cache rules
  for the service worker, manifest and build contract.
- `compose.yaml` runs `api`, `web`, and an optional scheduled `backup` sidecar on
  a separate profile. Only the web tier is published.
- SQLite keeps WAL, foreign keys, `NORMAL` synchronous mode and a configurable
  `busy_timeout` (default 5000 ms).
- `scripts/backup.py` and `scripts/restore.py` use the SQLite online backup API,
  checksum archives, and preserve replaced targets as `.pre-restore-*`.
- Structured JSON logs and `X-Request-ID` correlation are installed globally;
  optional Sentry initialises only when a DSN is set and the SDK is installed.
- `.env.example` documents every `Settings` field, including production,
  logging, backup and Compose-only values.
- Performance is executable: `scripts/performance_check.py` enforces the backend
  targets and `frontend/scripts/check-bundle-size.mjs` enforces the initial JS
  budget.
- `docs/runbook-cutover.md` is finalized and `docs/performance.md` records the
  targets and current measurements.

A review of the deployment surface found no code defects. The only material
gaps are environmental: no container runtime and no external proxy/Lighthouse
run in this sandbox.

## 2. Files added or changed

### Deployment and runtime

- `compose.yaml` — api/web/backup services, named data and backup volumes,
  readiness health check, internal-only API.
- `Dockerfile.api`, `Dockerfile.web`, `.dockerignore`.
- `backend/docker-entrypoint.sh` — migration gate, writable data check, one
  worker, no trusted proxy headers.
- `frontend/nginx.conf` — SPA fallback, `/api` proxy, cache policy, gzip,
  upload size, security headers, health probe.
- `backend/app/core/logging.py` — context-variable request ids, JSON/text
  formatters, request completion/failure logs, response header.
- `backend/app/core/observability.py` — optional Sentry initialisation with a
  missing-SDK warning instead of a startup failure.
- `backend/app/core/config.py` — logging, request-id, Sentry, SQLite timeout
  settings and validators.
- `backend/app/core/database.py` — configurable `PRAGMA busy_timeout`.
- `backend/app/main.py` — logging/Sentry setup and request middleware.
- `.env.example` — complete documented template; checked against every
  `Settings` field.
- `Makefile` — `performance`, `backup`, `restore` targets.
- `.github/workflows/ci.yml` — initial bundle budget runs after the frontend
  build.
- `backend/README.md` — production section and operational script examples.

### Operations and performance

- `backend/scripts/backup.py` — online SQLite backup, uploads archive,
  per-artifact SHA-256 and table counts.
- `backend/scripts/restore.py` — manifest/checksum validation, safe tar
  extraction, dry run, atomic replacement with preservation of old targets.
- `backend/scripts/performance_check.py` — 10,000-expense page p95, 50-operation
  sync push, 1,000-expense bootstrap.
- `frontend/scripts/check-bundle-size.mjs` — gzip initial-JS budget from
  `dist/index.html` entry + modulepreload chunks.
- `docs/performance.md` — targets, commands and Stage 12 measurements.
- `docs/runbook-cutover.md` — finalized cutover, rollback, backup/restore,
  monitoring and drill procedure.
- `docs/security.md` — backup script, single-writer timeout, log hygiene and
  Compose exposure checklist.

### Tests and formatting

- `backend/tests/test_backup.py` — round trip, tamper detection, dry run,
  missing/uploads validation, traversal rejection.
- `backend/tests/test_observability.py` — generated/preserved/rejected request
  ids, custom header, JSON formatter, middleware registration, Sentry fallback,
  settings validation.
- `backend/tests/test_deployment.py` — Compose invariants, Dockerfiles,
  nginx policy, `.dockerignore`, complete `.env.example`, operational assets.
- `backend/tests/test_database.py` — WAL/foreign-keys/busy-timeout/synchronous.
- Formatted pre-existing files (`generate_domain_fixtures.py`,
  `test_groups_sync.py`, `test_receipts.py`) so `ruff format --check .` is green;
  no behavior changes.

## 3. Commands run and output

### Import and verification on the confirmed fixture

```text
$ cd backend
$ PYTHONPATH=. .venv-work/bin/python scripts/import_legacy_sqlite.py \
    --source tests/fixtures/legacy/legacy_fixture.db --target /tmp/stage12/new.db
Imported .../legacy_fixture.db -> /tmp/stage12/new.db
  checksum: 04d55380a48cee62aad159c1f401d47e1ed7f3067ca8a890ecccd9a8847f9e01
  duration: 384 ms
  accounts: 2, activities: 3, categories: 44, expense_documents: 2,
  expense_paid_for: 20, expenses: 9, groups: 2, participants: 4,
  receipt_item_portions: 4, receipt_items: 3, receipt_opt_outs: 1,
  receipts: 2, recurring_expense_links: 2, user_groups: 3, users: 2
  seeded categories: 40

$ PYTHONPATH=. .venv-work/bin/python scripts/verify_import.py \
    --old tests/fixtures/legacy/legacy_fixture.db --new /tmp/stage12/new.db
  ok: row equality: 15 table(s) compared
  ok: per-group participant/expense aggregates compared
  ok: integrity_check and foreign_key_check
  ok: balances vs golden: /workspace/shared/fixtures/legacy/balances-legacy-fixture.json
PASS: import verified (2 group(s))

$ sqlite3 /tmp/stage12/new.db "PRAGMA foreign_key_check; PRAGMA integrity_check;"
ok
```

The legacy fixture is used because the confirmed `spliit-data/` database is not
mounted in this sandbox. The production-copy dry run remains a staging gate.

### Backup/restore/rollback data-path rehearsal

```text
backup_dir=/tmp/stage12-drill/backups/pysplit-backup-20261030T101321Z-drill
original_name=Cabin trip
test_write_rows=1
reimport_test_write_rows=0
elapsed_ms=2039
```

Sequence: backup fixture → verified restore → import → verify → inject a test
write into the new database → re-import from the untouched old database → verify
→ confirm the test write is absent. A fresh import verified both times; the
second verification fell back to comparing target to source because the restored
SQLite file has a different file checksum than the canonical golden fixture.

### Production-shaped local API

```text
$ ENVIRONMENT=production DATABASE_URL=sqlite:////tmp/stage12-prod/pysplit.db \
  UPLOAD_DIR=/tmp/stage12-prod/uploads BASE_URL=http://127.0.0.1:8899 \
  JWT_SECRET=0123456789abcdef0123456789abcdef LOG_FORMAT=json \
  ENABLE_MOCK_LOGIN=false
$ .venv-work/bin/alembic upgrade head
$ .venv-work/bin/uvicorn app.main:app --host 127.0.0.1 --port 8899 --workers 1 \
    --no-access-log --no-proxy-headers
{"status":"ready","checks":{"database":"ok"}}
x-request-id: 91d7f7fec87149a8bbf56ffc50ce7c9a
{"timestamp":"2026-10-30T10:13:33+0000","level":"INFO","logger":"pysplit.request",
 "message":"request.complete","request_id":"2af7291f17814cad8b27a284acbdb45c",
 "event":"request.complete","method":"GET","path":"/api/health/readiness",
 "status_code":200,"duration_ms":17.87,"client":"127.0.0.1"}
```

### Backend suite and quality

```text
$ cd backend && PYTHONPATH=. .venv/bin/pytest -q -n auto
346 passed, 2 skipped in 10.23s
Required test coverage of 80% reached. Total coverage: 92.82%
(skips are the pre-existing absent reference fixture database)

$ .venv/bin/ruff check .
All checks passed!
$ .venv/bin/ruff format --check .
148 files already formatted
```

### Frontend suite and quality

```text
$ cd frontend && npm test -- --run
Test Files  40 passed (40)
     Tests  145 passed (145)

$ npm run lint
Found 0 warnings and 0 errors.

$ npm run typecheck
tsc -p jsconfig.json            # no diagnostics

$ npm run build
✓ built in 184ms
PWA v2.0.0: precache 90 entries (1551.11 KiB)

$ npm run check:bundle
Initial JavaScript: 194.3 KiB gzip (198915 bytes)
Budget:            300.0 KiB gzip (307200 bytes)
OK: initial JavaScript is within budget.
```

### Backend performance targets

```text
$ cd backend
$ PYTHONPATH=. .venv-work/bin/python scripts/performance_check.py --json
Expense page p95: 6.78 ms (budget 300 ms)
50-op sync push:  117.24 ms (budget 500 ms)
Bootstrap 1,000:  131.47 ms (budget 1000 ms)
"passed": true, "failures": []
```

### Architecture and parity

```text
$ python3 scripts/check_architecture.py
OK: architecture boundaries, repository files, locales and e2e specs are consistent.

$ python3 scripts/check_parity_matrix.py
note: spliit/ is absent; checking coverage against docs/reference-manifest.txt
OK: 123 features; 14 pages, 28 procedure files, 30 Jest suites, 14 Playwright specs all mapped.
```

### Full Playwright suite

```text
$ BASE_URL=http://127.0.0.1:5173 npx playwright test --workers=2
Running 59 tests using 2 workers
  4 skipped
  55 passed (2.5m)

$ BASE_URL=http://127.0.0.1:4173 PWA_E2E=1 npx playwright test \
    e2e/pwa.spec.ts e2e/pwa-offline.spec.ts --workers=1
  4 passed (17.1s)
```

The 4 dev-server skips are the production-PWA specs; they were run separately
against `vite preview` and all passed. This covers all 59 tests in `e2e/`.

### Container verification (blocked)

```text
$ command -v docker podman buildah nerdctl containerd ctr
(no output; no /var/run/docker.sock)
```

`docker compose build`, `docker compose up -d`, the readiness curl through
nginx, and the proxy-switch rollback drill could not run here. Compose YAML and
all deployment invariants are covered by `backend/tests/test_deployment.py`, but
image builds and container startup must be repeated on staging.

## 4. Gate checklist

| Gate | Status |
|---|---|
| Production Compose with api/web and optional backup | PASS — static invariants tested |
| API image: Python 3.12 slim, Uvicorn, one worker, SQLite volume, readiness | PASS (source) / BLOCKED (image build) |
| Web image: nginx SPA fallback, `/api` proxy, compression, hashed caching | PASS (source) / BLOCKED (image build) |
| Dockerfiles and `.dockerignore` | PASS — tests assert pieces; image build BLOCKED |
| Complete `.env.example` | PASS — every `Settings` field documented |
| SQLite WAL, busy timeout, foreign keys, short transactions | PASS — pragma test; one-worker entrypoint |
| Backup/restore scripts and uploads archive | PASS — unit tests plus data-path rehearsal |
| Structured logs, request ids, optional Sentry | PASS — unit tests, local production run; SDK optional |
| Final cutover/rollback runbook | PASS — `docs/runbook-cutover.md` |
| Security checklist | PASS for code/config; TLS/proxy checklist is operator-owned |
| Page p95 < 300 ms with 10,000 expenses | PASS — 6.78 ms locally |
| 50-op sync push < 500 ms | PASS — 117.24 ms locally |
| 1,000-expense bootstrap < 1 s | PASS — 131.47 ms locally |
| Initial JS < 300 KB gzip | PASS — 194.3 KiB |
| Offline boot < 2 s / Lighthouse installable | NOT MEASURED here — PWA e2e passes; measure on staging |
| Full Playwright suite | PASS — 55 online + 4 PWA = 59/59 |
| Import verification on production copy | PARTIAL — fixture verified; production copy unavailable |
| Docker dry run on production copy | BLOCKED — no container runtime |
| Rollback drill with proxy switch | PARTIAL — data path 2.0 s; proxy/container path BLOCKED |
| User sign-off | PENDING |

## 5. Deviations and open questions

- **No container runtime in the sandbox.** Images, Compose health checks, nginx
  and the proxy switch were not executed. Static deployment tests reduce the
  risk but do not replace `docker compose build && up` on staging.
- **No production copy of the legacy database.** Import/verify used the committed
  edge-case fixture. The Stage 12 verification command must be rerun with
  `prod-copy.db` on staging.
- **Sentry SDK is intentionally optional.** `SENTRY_DSN` logs a warning and
  disables reporting if `sentry-sdk` is absent. If the deployment wants Sentry
  enabled, add a pinned `sentry-sdk` to `requirements.txt`; this was left out to
  avoid an external dependency for self-hosted installs that do not use it.
- **Lighthouse PWA and offline boot timing** need a real phone/profile on
  staging; `e2e/pwa*.spec.ts` and the bundle/backend budgets are green.
- **Compose backup sidecar uses a shell loop**, not a host cron. It shares the
  data volume read-only and writes checksummed backups to a separate volume;
  copy that volume off-host. A failed backup does not stop the API.
- **nginx terminates no TLS.** HTTPS and HSTS are owned by the edge proxy.
- **Proxy headers are not trusted by Uvicorn.** The application honours
  `X-Forwarded-*` only when `TRUST_FORWARDED_HEADERS=true`; Compose enables it
  because nginx overwrites the headers and the API is not published.
- The pre-existing `generate_domain_fixtures.py` RUF005 and three files with
  formatting drift were corrected so the repository-level `ruff check` and
  `ruff format --check` gates are green.

## 6. Intentionally deferred

- Archiving/removing the Node application and updating the root README —
  Stage 13.
- Final production cutover, real proxy switch, production-copy import and user
  sign-off — staging/production operations after this stage.
- Adding Sentry as a mandatory dependency and uploading source maps — optional
  follow-up.
