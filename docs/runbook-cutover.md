# Cutover and rollback runbook (outline)

Status: outline for Stage 12; rehearsed and signed off before Stage 13.
Related: ADR 0000 decision 6, MIGRATION_PLAN.md Stage 12.

The cutover is a **short maintenance window**, not a dual run. There is no
bidirectional bridge. The old Node application stays stopped for seven days and
its database and uploads remain untouched as the rollback source.

## 0. Pre-conditions

- [ ] Stage 12 dry run passed on a copy of the production database.
- [ ] Import verification: zero missing rows, zero FK violations, matching
      per-group counts/sums/balances, `integrity_check = ok`.
- [ ] Full Playwright suite (14 reference + 4 new specs) green in staging.
- [ ] PWA install/offline/update checks green.
- [ ] Auth/RBAC matrix green; production refuses the development JWT secret.
- [ ] Backups tested by restoring into a scratch directory.
- [ ] Rollback owner and decision threshold agreed.
- [ ] Users notified of the maintenance window.

## 1. Announce maintenance

Post the window and expected read-only/offline period. Export or synchronize
any data the team needs during the window. Do not start the window until the
rollback artifacts exist.

## 2. Stop the old application

Stop the Node container/process and the reverse proxy upstream. Confirm the
health endpoint is no longer served by the old stack. Leave its volumes and
database in place.

## 3. Back up

1. SQLite online backup of the production database (`.backup` or the SQLite
   backup API; do not copy a live WAL file without the checkpoint).
2. Archive uploads/documents and the old `.env` (secrets are inventory, not
   content).
3. Record SHA-256 checksums of every backup artifact.
4. Copy backups off the host and verify readability.

## 4. Import and verify

```bash
backend/.venv/bin/python backend/scripts/import_legacy_sqlite.py \
  --source /backups/spliit.db --target /data/pysplit.db
backend/.venv/bin/python backend/scripts/verify_import.py \
  --old /backups/spliit.db --new /data/pysplit.db
sqlite3 /data/pysplit.db "PRAGMA foreign_key_check; PRAGMA integrity_check;"
```

Abort and roll back if any count, sum, balance or integrity check fails. Do not
"fix up" production data interactively.

## 5. Start the new stack

```bash
docker compose up -d
curl -f http://localhost:8080/api/health/readiness
```

Smoke test, in this order:

1. `GET /api/health`, liveness, readiness.
2. Open an existing shared group URL and confirm participants/expenses.
3. Create and delete a test expense; confirm activity.
4. Check balances and statistics against the golden fixture.
5. Log in with a pre-authorized admin; open `/api/admin/metrics`.
6. Upload and scan a receipt (if AI is configured) or confirm flags are off.
7. Export CSV/JSON and compare headers/format.

## 6. Switch the reverse proxy

Point the public hostname at the new `web` service. Keep the old upstream
configuration saved. Verify HTTPS, cookies (`HttpOnly; Secure; SameSite=Lax`),
CORS allowlist, and that `/api` is proxied, not served by nginx from disk.

## 7. Monitor

Watch for 30–60 minutes:

- 5xx rate, readiness failures, SQLite `busy`/lock errors;
- import counts in `ImportRun`;
- auth refresh failures and OAuth callback errors;
- sync push errors/conflicts;
- upload failures and AI `FAILED` receipts;
- browser console errors and service-worker update loops.

## 8. Rollback

Trigger rollback if any of the following holds:

- readiness is not stable;
- data loss or a balance mismatch is detected;
- login is broken for admins or a majority of users;
- writes fail persistently (SQLite contention, migration defect);
- a security issue is found in the new auth/cookie path.

Rollback steps:

1. Point the reverse proxy back to the stopped old upstream.
2. Start the old application from its untouched volumes.
3. Verify the old app health and a known group.
4. Preserve the failed new database and logs for diagnosis.
5. Announce restoration and open an incident note.

Rollback does not require re-importing data because the old database was never
modified. If the old app accepted writes after cutover by mistake, stop and
reconcile manually before retrying.

## 9. After a successful cutover

- Keep the old stack stopped for seven days.
- Disable old CI/deploy jobs.
- Archive `spliit/` on a tag/branch and retain the importer and fixtures.
- Update the root README with architecture, development, deployment, backups,
  AI configuration and offline behavior (Stage 13).
- Record recovery time and any deviations in the Stage 12 report.

## 10. Rollback drill

Before production, perform the drill on staging:

1. Cut over to the new stack.
2. Make a test write.
3. Roll back to the old stack and verify the old data is intact.
4. Cut over again and verify the test write is absent (expected) and the import
   is reproducible.
5. Record elapsed time for stop, backup, import, start, proxy switch and
   rollback.

Target: restore the old application in under 15 minutes with zero data loss.
