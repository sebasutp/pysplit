# Stage 6 report — server-side synchronization protocol

Date: 2026-10-24
Stage: 6 (bootstrap, pull, push, conflicts, idempotency, compaction)

## Outcome

The backend now implements the synchronization contract from plan §2.5 and
ADR 0002:

- `GET /api/sync/bootstrap` returns a full group snapshot (group, live
  participants, active expenses, activities, receipts/items/portions/opt-outs,
  categories and the authenticated user's membership) plus the current cursor.
- `POST /api/sync/pull` returns full-snapshot changes after a validated cursor
  with stable pagination and `has_more`.
- `POST /api/sync/push` applies up to 50 operations independently, records each
  result for seven days, appends change-log rows, and returns per-operation
  `applied`/`conflict`/`error` results.
- Entity/field whitelists cover `group`, `participant`, `expense` and
  `user_group`; unknown entity types and unknown top-level/nested fields are
  rejected per operation.
- Expense updates/deletes enforce `base_version`; stale writes return the
  current server snapshot. Group metadata, participant names and star/archive
  membership use last-writer-wins. Deletes are tombstones.
- Duplicate creates are idempotent by operation ID and by client-generated
  entity ID, including concurrent writers racing on the same ID.
- `claim_groups` provides the account merge/claim service used by later login
  and device-sync work.
- Expired and future cursors return `409 {"detail": "bootstrap_required"}`.
- Change-log compaction writes a `sync_meta` marker so the retained window is
  machine-verifiable.
- Recurrence materialization now appends a change-log row for every generated
  frame, so pull-only clients see server-created recurring expenses.

## Files added

- `backend/app/api/sync.py` — HTTP endpoints only.
- `backend/app/schemas/sync.py` — push/pull/bootstrap request and response
  models.
- `backend/app/services/sync.py` — whitelists, per-entity apply functions,
  idempotency, conflicts, cursor validation, compaction and group claims.
- `backend/tests/test_sync.py` — protocol, bootstrap, tombstones, pagination,
  validation, claim/merge and replay tests.
- `backend/tests/test_sync_conflicts.py` — conflict resolution, delete-vs-update,
  two-client convergence, replay and concurrent recurrence tests.
- `docs/stage-6-report.md` — this report.

## Files changed

- `backend/app/core/config.py` — `SYNC_OPERATION_RETENTION_DAYS` (7) and
  `SYNC_CHANGE_RETENTION_DAYS` (30) with positive-value validation.
- `backend/app/main.py` — registers the sync router.
- `backend/app/services/groups.py` — `commit=False` support for transaction-owning
  callers; live-participant filtering for tombstones.
- `backend/app/services/expenses.py` — `commit=False` support; deleted
  participants are excluded from new expense validation; recurrence frames
  write change-log rows.
- `backend/app/services/categories.py` — default-category seeding can flush
  instead of committing inside a sync transaction.
- `backend/tests/test_architecture.py` — includes `api/sync.py` in the
  HTTP-only router check and asserts the Stage 6 specs exist.
- `docs/api.md` — documents supported entities, payload fields, LWW/conflict
  behavior and the `bootstrap_required` response.
- `docs/openapi.json` — regenerated snapshot with the three sync paths.
- `docs/parity-matrix.yml`, `docs/parity-report.md` — six Stage 6 feature rows:
  `SYNC-PUSH`, `SYNC-PULL`, `SYNC-BOOTSTRAP`, `SYNC-CONFLICT`, `SYNC-CLAIM`,
  `SYNC-COMPACTION`.
- `.env.example`, `backend/.env.example` — synchronization retention settings.

No database migration was required: `sync_changes`, `sync_operations` and the
versioning columns already exist in `0003_sync_and_auth_schema`. `alembic
check` reports no new upgrade operations.

## Design details

### Per-operation transaction

Mutating group/expense services accept `commit: bool = True`. The sync service
passes `commit=False`, appends the change-log row(s), writes the idempotency
result, then commits once. On `SyncError`, `SyncConflict`, Pydantic
`ValidationError` or `IntegrityError`, only that operation's transaction is
rolled back; earlier operations in the same HTTP request remain committed.

Default-category seeding is flushed rather than committed when called inside a
sync operation, so the expense and its change-log row stay atomic.

### Idempotency and ordering

- `sync_operations` is checked before applying an operation. A live row returns
  the stored result verbatim.
- Results are retained for seven days; expired rows are deleted by compaction.
- Applied operations append one or more `sync_changes` rows and return the
  primary sequence number plus the latest feed cursor.
- Duplicate creates return `status: "applied"`, `duplicate: true`, and the
  existing snapshot without appending a second change.
- A concurrent primary-key race is treated as an idempotent duplicate.

### Cursor and compaction

- Pull cursors must be within the retained feed. A cursor older than the
  compaction floor, older than a gap in the oldest retained sequence, or newer
  than the server feed receives `409 bootstrap_required`.
- Compaction removes change rows older than 30 days and writes a
  non-returnable `sync_meta/change_log` marker containing
  `{"compacted_through": <seq>}`.
- Cursors are per requested `group_ids` scope; pull returns the last returned
  sequence rather than skipping changes for groups the caller did not request.

### Conflict rules

| Entity | Behavior |
|---|---|
| `group` | metadata last-writer-wins; create requires creator/admin auth |
| `participant` | name last-writer-wins; delete soft-tombstones the row |
| `expense` | update/delete require matching `base_version`; stale writes conflict; tombstones win |
| `user_group` | per-user last-writer-wins; requires authentication; hidden from guest pulls |

## Verification commands and output

### Stage 6 suite (plan command)

```bash
$ cd backend
$ PYTHONPATH=. .venv-work/bin/pytest tests/test_sync.py tests/test_sync_conflicts.py -n auto
...
======================= 22 passed, 25 warnings in 3.13s ========================
```

The repository virtualenv is the known sandbox artefact documented in the
Stage 5 report; `.venv-work/bin/pytest` is the working interpreter behind
`backend/.venv`.

### Full backend suite with coverage

```bash
$ PYTHONPATH=. .venv-work/bin/pytest -n auto
...
TOTAL                                   4259    317    93%
Required test coverage of 80% reached. Total coverage: 92.56%
======================= 209 passed, 25 warnings in 8.63s =======================
```

### Lint and formatting

```bash
$ .venv-work/bin/ruff check .
All checks passed!

$ .venv-work/bin/ruff format --check .
120 files already formatted
```

### Alembic

```bash
$ DATABASE_URL=sqlite:////tmp/stage6-alembic.db .venv-work/bin/alembic upgrade head
... Running upgrade 0002_receipts_schema -> 0003_sync_and_auth_schema
$ DATABASE_URL=sqlite:////tmp/stage6-alembic.db .venv-work/bin/alembic check
No new upgrade operations detected.
```

### OpenAPI

```bash
$ backend/.venv-work/bin/python backend/scripts/export_openapi.py
Wrote docs/openapi.json (41 paths)
```

`tests/test_openapi.py` passes in the full suite; the snapshot now contains
`/api/sync/bootstrap`, `/api/sync/pull` and `/api/sync/push`.

### Parity matrix

```bash
$ backend/.venv-work/bin/python scripts/check_parity_matrix.py
OK: 117 features; 14 pages, 28 procedure files, 30 Jest suites, 14 Playwright specs all mapped.
```

### Two-client convergence scenario

`test_two_clients_converge_and_replay_delete_once` runs the gate scenario:

1. client A creates an expense;
2. client B pulls and updates it;
3. client A's stale update returns a conflict;
4. A pulls the server edit and updates again;
5. B pulls A's edit and deletes the expense;
6. A pulls the tombstone;
7. B replays the delete and receives the stored result.

Both clients reconstruct the same final snapshot. The server holds one expense
at version 4 with `deleted_at` set and exactly four change-log rows
(create/update/update/delete).

## Gate checklist

| Gate item | Status |
|---|---|
| Bootstrap returns a full snapshot and current cursor | Pass |
| Pull validates cursors, returns snapshots, paginates and sets `has_more` | Pass |
| Push accepts at most 50 operations and answers each independently | Pass |
| Replayed operation applies once and returns the stored result | Pass |
| Duplicate create (new operation ID) returns the existing row | Pass |
| Stale expense update/delete returns `conflict` with `server_entity` | Pass |
| Delete versus update honors the tombstone | Pass |
| Tombstones survive pull after the create cursor | Pass |
| Expired and future cursors require bootstrap | Pass |
| Cross-group operations are rejected | Pass |
| Unknown entity types, top-level fields and nested fields are rejected | Pass |
| Concurrent same-ID pushes create one expense and one recurrence link | Pass |
| One invalid operation does not roll back other operations | Pass |
| Group metadata, participant names and membership use LWW | Pass |
| Group creation is tier-gated and creates participants atomically | Pass |
| Group claim/merge is idempotent and writes change rows | Pass |
| Change-log compaction records the compacted floor | Pass |
| Materialized recurrence frames appear in pull | Pass |
| Architecture check keeps the sync router HTTP-only | Pass |
| Full suite, coverage, lint, format, Alembic, OpenAPI and parity checker green | Pass |

**Gate: PASSED.**

## Deviations and open questions

1. **Participant deletion is a soft tombstone in the sync path.** The existing
   `DELETE /api/groups/{id}/participants/{id}` endpoint still hard-deletes and
   cascades per the reference schema. Sync deletes set `deleted_at` so a pull
   can deliver the tombstone and so historical expenses are not silently
   removed by an offline action. Group/expense reads hide tombstoned
   participants. If the reference's cascade semantics must apply to sync
   deletes too, Stage 9/11 should decide whether to hard-delete and emit
   cascading expense tombstones.
2. **`user_group` deletes are hard deletes with a synthetic tombstone
   snapshot.** Star/archive membership is LWW, so clients apply the tombstone
   regardless of version. Re-claiming the same group creates a fresh row with
   version 1. This is sufficient for Stage 11's claim/merge flow but should be
   revisited if membership version history is needed.
3. **Cursor-expiry response is `409` with `detail: "bootstrap_required"`.**
   The plan did not prescribe a status code. The detail string is the stable
   machine-readable signal documented in `docs/api.md`.
4. **Compaction runs opportunistically at push/pull/bootstrap entry points.**
   A scheduled maintenance job is deferred to the deployment stage; correctness
   does not depend on the schedule because every protocol entry point enforces
   the same floor.
5. **Receipt mutations are deferred to Stage 7.** Bootstrap already includes
   receipts, items, portions and opt-outs. Push/pull apply functions for
   `receipt`, `receipt_item`, `receipt_item_portion` and `receipt_opt_out` are
   intentionally reserved for Stage 7's receipt API work.
6. **No sync rate limit yet.** The plan lists synchronization push rate limits
   in the security checklist; Stage 6 adds the protocol, and the shared limiter
   integration belongs with the Stage 12 security pass.
7. **Group update with an empty payload still increments the version and logs
   an activity.** This follows the existing Stage 5 service behavior. Clients
   should omit no-op updates; the protocol accepts them deterministically.
8. **No real two-device HTTP concurrency harness.** The concurrency test uses
   two SQLite connections and two service calls in separate threads against a
   temporary file database. It verifies the unique-key/idempotency behavior
   without depending on TestClient thread-safety.

## Intentionally deferred

- Receipt/portion/opt-out push and pull entity appliers (Stage 7).
- Client outbox, Dexie repository, sync status and conflict UI (Stage 9B).
- Authenticated cross-device group list synchronization endpoint/UI wiring
  (Stage 11); the underlying `claim_groups` service is ready.
- Scheduled compaction, sync rate limiting, structured logs and production
  deployment tuning (Stage 12).
