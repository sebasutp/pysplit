# Cutover and rollback runbook

Status: production entrypoint implemented in Stage 12. The orchestrated Docker
dry run and proxy switch were **not** executed in the development sandbox
(no container runtime); the data-path rehearsal and all local gates are recorded
in `stage-12-report.md`.

Related: ADR 0000 decision 6, `compose.yaml`, `docs/security.md`,
`docs/performance.md`, and `MIGRATION_PLAN.md` Stage 12/13.

The cutover is a **short maintenance window**, not a dual run. There is no
bidirectional bridge. The old Node application stays stopped for seven days and
its database and uploads remain untouched as the rollback source.

## 0. Pre-conditions

- [ ] Stage 12 dry run passed on a **copy** of the production database; import
      verification shows zero missing rows, zero FK violations, matching
      per-group counts/sums/balances, and `integrity_check = ok`.
- [ ] Full Playwright suite green in staging, including PWA and offline specs.
- [ ] Performance targets in `docs/performance.md` were measured on staging-sized
      data and passed.
- [ ] Auth/RBAC matrix green; production refuses the development JWT secret.
- [ ] Backups were restored into a scratch directory, and the offline upload
      archive was inspected.
- [ ] Rollback owner and decision threshold are agreed.
- [ ] Users received the maintenance announcement and the expected window.
- [ ] The edge proxy configuration for the old upstream was saved.

Record the rollback owner, start time, and decision threshold here for the
actual run:

```text
Rollback owner: ______________________
Window:         ______________________
Abort if:       readiness unstable > 5 min, any balance mismatch, admin login
                broken, persistent write failures, or a security defect.
```

## 1. Announce maintenance

Post the window and expected read-only/offline period. Export or synchronize
anything the team needs during the window. Do not start until the rollback
artifacts and the old stack are confirmed restartable.

## 2. Stop the old application

Stop the Node container/process and the reverse-proxy upstream. Confirm the
public health endpoint is no longer served by the old stack. Leave its volumes,
database and uploads in place.

## 3. Back up the old stack

Use the backup script with paths pointing at the **old** database and uploads.
It uses the SQLite online backup API, so it is safe if a final read arrives
during the stop, and it records SHA-256 checksums for every artifact.

```bash
cd /workspace/backend
PYTHONPATH=. .venv/bin/python scripts/backup.py \
  --database /old-data/spliit.db \
  --uploads /old-data/uploads \
  --output /backups/pre-cutover \
  --label pre-cutover
```

The command prints the backup directory and checksums. Also copy the old `.env`
to the secret inventory (not to a ticket or chat), record the Compose/proxy
files, and copy all artifacts off-host. Verify a restore of the new backup into
a scratch path before proceeding:

```bash
PYTHONPATH=. .venv/bin/python scripts/restore.py \
  --backup /backups/pre-cutover/pysplit-backup-... \
  --database /tmp/restore-check/spliit.db \
  --uploads /tmp/restore-check/uploads \
  --dry-run
```

A `--dry-run` validates the manifest, sizes and checksums without replacing
files. Then perform one real restore into `/tmp/restore-check` and open the
database with `sqlite3` to confirm the expected tables and counts.

If the old application uses a live WAL, do **not** copy `spliit.db` with `cp`.
The backup script includes the WAL via the SQLite backup API; a raw copy requires
a checkpoint first.

## 4. Import and verify

Import and verify into a host staging directory first. The production database
lives in the `pysplit_data` Docker volume, not at the host `/data` path.

```bash
cd /workspace/backend
rm -rf /tmp/pysplit-import && mkdir -p /tmp/pysplit-import
PYTHONPATH=. .venv/bin/python scripts/import_legacy_sqlite.py \
  --source /tmp/restore-check/spliit.db \
  --target /tmp/pysplit-import/pysplit.db
PYTHONPATH=. .venv/bin/python scripts/verify_import.py \
  --old /tmp/restore-check/spliit.db \
  --new /tmp/pysplit-import/pysplit.db
sqlite3 /tmp/pysplit-import/pysplit.db \
  "PRAGMA foreign_key_check; PRAGMA integrity_check;"
```

Abort and roll back if any count, sum, balance or integrity check fails. Do not
"fix up" production data interactively. The importer refuses a non-empty target
unless `--reset` is supplied; `--reset` is for a retry of a failed import whose
backup still exists, never for a live database that might have accepted writes.

## 5. Start the new stack

Create the production environment file (never commit it) and fill the required
secret. The template already sets `ENVIRONMENT=production`, so the API refuses
to start without a valid `JWT_SECRET` and `BASE_URL`.

```bash
cd /workspace
cp .env.production.example .env
# Replace JWT_SECRET with: openssl rand -hex 32
# Replace BASE_URL with the public HTTPS origin.
```

Relevant values:

```dotenv
ENVIRONMENT=production
BASE_URL=https://spliit.example.com
JWT_SECRET=<unique, at least 32 characters>
COMPOSE_WEB_PORT=8080
LOG_FORMAT=json
ENABLE_MOCK_LOGIN=false
TRUST_FORWARDED_HEADERS=true
```

`compose.yaml` mounts the persistent `pysplit_data` volume at `/data`, runs the
API as a non-root user, applies Alembic migrations before starting Uvicorn with
one worker, and only publishes the nginx web tier. The API is not exposed to the
host.

```bash
cd /workspace
docker compose config                 # interpolation check
docker compose build
# Copy the verified staging database into the named volume as UID 10001.
docker run --rm --entrypoint python \
  -v pysplit_pysplit_data:/data \
  -v /tmp/pysplit-import:/import:ro \
  pysplit-api:local -c \
  "import shutil; shutil.copy2('/import/pysplit.db', '/data/pysplit.db')"
docker compose up -d
docker compose ps
curl -f http://localhost:8080/api/health/readiness
```

Start the optional scheduled backup sidecar:

```bash
docker compose --profile backup up -d backup
docker compose exec backup python /app/scripts/backup.py --help
```

The sidecar reads the same `DATABASE_URL` and `UPLOAD_DIR` as the API, backs
up every `BACKUP_INTERVAL_SECONDS` (default 24 h) into the `pysplit_backups`
volume, and deletes directories older than `BACKUP_RETENTION_DAYS` (default 14).
A missing uploads directory is logged and the database is still backed up. Copy
the backup volume off-host on the same schedule; a backup on the same disk is
not a disaster recovery plan.

Smoke test, in this order:

1. `GET /api/health`, `/api/health/liveness`, and `/api/health/readiness`.
2. Open an existing shared group URL and confirm participants and expenses.
3. Create and delete a test expense; confirm activity and balances.
4. Check statistics and suggested reimbursements against the golden fixture.
5. Log in with a pre-authorized admin; open `/api/admin/metrics`.
6. Upload and scan a receipt if AI is configured, otherwise confirm flags are
   off and manual entry works.
7. Export CSV/JSON and compare headers and formatting.
8. Reload an already-open group with the network disabled and confirm cached
   data.

## 6. Switch the reverse proxy

Point the public hostname at the new nginx service (`COMPOSE_WEB_PORT`, default
8080 on the host, port 80 in the container). Keep the old upstream configuration
saved. nginx replaces `X-Forwarded-For` with the direct peer address so clients
cannot spoof rate-limit identities. If a CDN or edge proxy sits in front of
nginx, configure `set_real_ip_from` / `real_ip_header` there so `$remote_addr`
is the real client. Verify:

- HTTPS terminates at the edge and redirects HTTP to HTTPS;
- cookies are `HttpOnly; Secure; SameSite=Lax` and scoped to `/api/auth` for
  refresh tokens;
- `/api` is proxied to the API and not served from disk;
- `Cache-Control: no-store` is present on API responses;
- `sw.js`, `manifest.webmanifest`, and `pwa-build.json` are not cached;
- hashed `/assets/*` responses are cached immutably;
- the CORS allowlist and `BASE_URL` match the public origin.

## 7. Monitor

Watch for 30–60 minutes:

- 5xx rate, readiness failures, SQLite `busy`/lock errors and request IDs;
- import counts in `ImportRun`;
- auth refresh failures and OAuth callback errors;
- sync push errors/conflicts and outbox depth;
- upload failures and AI `FAILED` receipts;
- browser console errors and service-worker update loops;
- disk usage for `/data` and `/backups`.

Structured logs are JSON in production (`LOG_FORMAT=json`) and include the
request id, method, path, status and duration. `X-Request-ID` is echoed to the
client. If `SENTRY_DSN` is set and `sentry-sdk` is installed, exceptions are also
reported without default PII.

## 8. Rollback

Trigger rollback on any condition in section 0. The old database was never
modified, so rollback does not require re-importing data.

1. Point the edge proxy back to the old upstream.
2. Start the old application from its untouched volumes.
3. Verify old-app health and a known group.
4. Stop the new stack but keep its `/data` volume for diagnosis.
5. Preserve logs and the new database; do not overwrite the backup.
6. Announce restoration and open an incident note.

If the old app did accept writes after cutover by mistake, stop and reconcile
manually before retrying. Do not run two writers against one database.

Restoring the new stack from its own backup, if that is ever needed:

```bash
cd /workspace
docker compose down
docker run --rm --entrypoint python \
  -v pysplit_pysplit_data:/data \
  -v pysplit_pysplit_backups:/backups \
  pysplit-api:local /app/scripts/restore.py \
  --backup /backups/pysplit-backup-... \
  --database /data/pysplit.db \
  --uploads /data/uploads
docker compose up -d
curl -f http://localhost:8080/api/health/readiness
```

`restore.py` verifies the manifest, checksums and SQLite integrity first. It
moves stale `-wal`/`-shm` sidecars aside with the old database and renames
existing targets to `.pre-restore-<timestamp>` siblings instead of deleting
them. Stop the API before restoring so the old SQLite file has no open writers.

## 9. After a successful cutover

- Keep the old stack stopped for seven days.
- Keep nightly backups and copy them off-host.
- Disable old CI/deploy jobs.
- Archive `spliit/` on a tag or branch and retain the importer and fixtures.
- Update the root README with architecture, deployment, backups, AI
  configuration and offline behavior (Stage 13).
- Record recovery time and deviations in the Stage 12 report.

## 10. Rollback drill

Run on staging after the production-shaped stack is built, not on production.

1. Cut over to the new stack.
2. Create a test expense and an image/PDF attachment.
3. Record the new write IDs.
4. Stop the new stack and point the proxy back to the old stack.
5. Start the old stack and verify its data is intact; the new test expense must
   not exist there.
6. Back up the old database with `scripts/backup.py`, restore it into a scratch
   directory, import into a fresh `/tmp` target, and verify with
   `scripts/verify_import.py` before copying it into a fresh volume.
7. Cut over again and confirm the re-import reproduces the pre-drill state; the
   test write was only in the discarded new volume.
8. Record elapsed time for stop, backup, import, start, proxy switch and
   rollback.

Target: restore the old application in under 15 minutes with zero data loss.
Record the measured timings in `stage-12-report.md` (or the incident log) before
claiming the gate.

## 11. Local data-path rehearsal (no container runtime)

Where Docker is unavailable, this proves the backup/import/restore sequence but
does not exercise nginx, Compose health checks or the proxy switch:

```bash
cd /workspace/backend
export PYTHONPATH=.
.venv/bin/python scripts/backup.py \
  --database tests/fixtures/legacy/legacy_fixture.db \
  --output /tmp/stage12/backups --label rehearsal
.venv/bin/python scripts/restore.py \
  --backup /tmp/stage12/backups/pysplit-backup-... \
  --database /tmp/stage12/old-restored.db
.venv/bin/python scripts/import_legacy_sqlite.py \
  --source /tmp/stage12/old-restored.db --target /tmp/stage12/new.db
.venv/bin/python scripts/verify_import.py \
  --old /tmp/stage12/old-restored.db --new /tmp/stage12/new.db
```

A container-runtime dry run is still required before production.
