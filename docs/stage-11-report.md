# Stage 11 report — Authenticated group sync and admin polish

Status: complete. The two-device synchronization gate passes.

## 1. Outcome

Login now claims the guest cache instead of wiping it. A guest-to-account
transition captures every locally known group ID plus the guest star/archive
preferences, writes account membership rows in place, enqueues durable
`user_group` outbox operations, and stores a `pending_group_merge` marker. The
normal sync cycle pushes those claims, then reconciles the complete account
group scope through `POST /groups/sync`, bootstraps the returned groups and
clears the marker. An offline login keeps the guest groups readable and retries
the merge when the API returns.

Star and archive remain arrival-order last-writer-wins per user: a stale
`user_group` base version applies, is scoped to the signed-in user, and does not
affect another user's membership. Star and archive are mutually exclusive; an
archive claim clears a star rather than leaving both flags set. Removing a
membership drops it from the synchronized list without deleting the group or
its expenses.

A review of the first cut found four correctness gaps, now addressed:

- An authenticated list read no longer sends cached recent IDs as claims.
  Previously another device's reload re-created a membership removed on the
  first device. `POST /groups/sync` now treats `group_ids` as a read filter and
  only `local_group_ids` (the explicit claim field) as membership creation.
- Guest preferences are sent as positive-only signals and the server enforces
  star/archive exclusion, so a guest archive cannot leave both flags set.
- A scope refresh only runs after a push cycle reports no errors, and the
  pending merge marker plus queued outbox work protect groups from pruning.
- Tests now cover the real merge path, cross-device removal, guest
  archive-versus-star, and stale-scope pruning; the gate claims below match
  those tests.

The existing admin UI already had metrics, paging, search, tier changes,
pre-authorization and deletion from Stage 8D. Stage 11 adds explicit coverage
that a tier change applies to the next request with an unchanged access token.

## 2. Files added or changed

### Frontend behavior

- `frontend/src/services/repository/local.js` — guest-cache capture and in-place
  claim, durable merge marker and `user_group` operations, `groups/sync`
  reconciliation, full-scope prefetch, authenticated cached-list fallback,
  merge-aware pruning and selection-key cleanup on removal.
- `frontend/src/services/repository/online.js` — explicit `local_group_ids`
  claim payload alongside the read-only `group_ids` filter.
- `frontend/src/services/sync.js` — group-scope reconciler hook run after each
  successful push/pull cycle, so a queued login merge completes after reconnect.
- `frontend/src/hooks/useGroups.js` — reloads the synchronized list after a
  background sync/login refresh and reconciles stale recent/star/archive keys
  against the authenticated scope.
- `frontend/src/services/repository/local.test.js` — authenticated list reads
  do not claim cached IDs; removal clears local selection keys.
- `frontend/src/services/group-sync.test.js` — unit coverage for positive-only
  guest preferences, guest-cache retention, queued merge, failed-request retry
  and stale-scope pruning protection.

### Backend behavior and verification

- `backend/app/services/groups.py` — `group_ids` no longer claims membership;
  explicit `local_group_ids` remains the merge field. Membership writes keep
  star/archive exclusive.
- `backend/app/services/sync.py` — `user_group` push and group claim enforce
  star/archive exclusion; archive wins when both are supplied.
- `backend/tests/test_groups_sync.py` — Stage 11 suite for a push/pull
  second-device read, per-user LWW star/archive, guest archive versus an
  existing star, read-only list IDs, and membership removal preserving data.
- `backend/tests/test_admin.py` — asserts an admin promotion takes effect on the
  next request with the same token.
- `backend/tests/test_architecture.py` — requires the Stage 11 test modules.

### End-to-end and architecture

- `frontend/e2e/group-sync.spec.ts` — five two-context scenarios: create and
  star visible on the second device; removal on one device not undone by the
  other's reload; guest group (with an expense) claimed on login once; guest
  archive not leaving star and archive both set; queued login merge claimed
  after synchronization returns.
- `frontend/src/architecture.test.js`, `scripts/check_architecture.py` — require
  `e2e/group-sync.spec.ts`.
- `scripts/check_parity_matrix.py` — treats an empty `spliit/` directory as an
  absent reference tree for both discovery and `--write-reference-manifest`, so
  the committed reference manifest stays authoritative in this sandbox.

### Documentation

- `docs/offline-capabilities.md` — login/merge is now online, offline and
  queued; describes the guest-cache exception, retry behavior, pruning
  protection and arrival-order LWW.
- `docs/repository-contract.md` — documents guest-to-account merge semantics,
  in-place updates, read-versus-claim IDs, mutual exclusion and LWW membership.
- `docs/api.md` — clarifies that `group_ids` is a read filter and
  `local_group_ids` is the claim field.

## 3. Commands run and output

```text
$ cd frontend && npm test -- --run
Test Files  40 passed (40)
     Tests  145 passed (145)

$ npm run lint
Found 0 warnings and 0 errors.

$ npm run typecheck
tsc -p jsconfig.json            # no diagnostics

$ npm run build
✓ built in 274ms
PWA v2.0.0
mode      generateSW
precache  90 entries (1551.11 KiB)
files generated
  dist/sw.js
  dist/workbox-2c475f06.js

$ export LD_LIBRARY_PATH="$(find /workspace/.cache/libs/extract \
    -type d -path '*/usr/lib/x86_64-linux-gnu' | paste -sd:)"
$ BASE_URL=http://127.0.0.1:5173 npx playwright test \
    e2e/group-sync.spec.ts e2e/admin.spec.ts --workers=1
7 passed (20.9s)

$ BASE_URL=http://127.0.0.1:5173 npx playwright test \
    e2e/group-management.spec.ts e2e/global-balance.spec.ts \
    e2e/offline-sync.spec.ts --workers=1
13 passed, 1 failed (1.4m)

$ BASE_URL=http://127.0.0.1:5173 npx playwright test \
    e2e/global-balance.spec.ts:49 --workers=1
1 passed (5.7s)

$ cd ../backend
$ PYTHONPATH=. .venv/bin/pytest -q tests/test_admin.py \
    tests/test_groups_sync.py tests/test_group_sync.py \
    tests/test_rbac.py tests/test_sync.py tests/test_sync_conflicts.py
62 passed, 1 warning

$ PYTHONPATH=. .venv/bin/pytest -q -n auto
323 passed, 2 skipped (reference fixture database absent)
Coverage: 92.88%

$ cd .. && python3 scripts/check_architecture.py
OK: architecture boundaries, repository files, locales and e2e specs are consistent.

$ python3 scripts/check_parity_matrix.py
note: spliit/ is absent; checking coverage against docs/reference-manifest.txt
OK: 123 features; 14 pages, 28 procedure files, 30 Jest suites, 14 Playwright specs all mapped.
```

The adjacent Playwright run had one `global-balance` failure caused by a
refresh-token 401 during the shared `e2e-creator` account login, not by a group
assertion; the failing test passed alone immediately afterwards. The full
Stage 11 group-sync suite was green on both runs. This is the same first-load
auth race noted below, now isolated to the shared test account rather than the
group list.

The e2e shell was launched with `./dev`; Chromium needed the sandbox's extracted
system libraries on `LD_LIBRARY_PATH`. That is an environment detail, not a
project change.

A broader optional `ruff check .` still reports one pre-existing `RUF005` in
`backend/scripts/generate_domain_fixtures.py:198`, a file not changed by this
stage. The Stage 11 backend gate command is pytest and is green.

## 4. Gate checklist

| Gate | Status |
|---|---|
| On login, local group IDs merge into `UserGroup` | PASS — in-place rows plus `user_group` outbox operations; explicit `local_group_ids` claim field |
| Merge is queued when offline | PASS — `pending_group_merge` + outbox rows; unit and e2e |
| User scope is bootstrapped and all groups pulled | PASS — reconcile calls `/groups/sync`, caches the full scope and prefetches returned groups |
| Guest cache is not duplicated | PASS — same group IDs updated in place; e2e asserts one group, one membership and the guest expense |
| Star/archive synchronizes as LWW per user | PASS — backend stale-version test; guest archive clears the star; two-device e2e |
| Remove group from synchronized list without deleting data | PASS — membership delete leaves group and expenses; removal on B is not undone by A's reload |
| Record access after a visit, debounced | PASS — retained debounced `groups.recordAccess` path; backend access test green |
| Global balance uses the active user and cached expenses | PASS — local `balances.forUser`; global-balance assertions pass, with the shared-account auth-refresh flake noted in §3 |
| Admin dashboard polished / tier changes immediate | PASS — existing Stage 8D dashboard; new next-request tier test and admin e2e |
| Two-device: create on A visible on B | PASS — push/pull test + `group-sync.spec.ts` |
| Two-device: star on A visible on B | PASS — `group-sync.spec.ts` |
| Guest group claimed on login without duplication | PASS — `group-sync.spec.ts`; no authenticated list claim remains |
| Offline login merge followed by reconnect | PASS — `group-sync.spec.ts` |
| Stale scope cannot prune a queued guest group or its writes | PASS — merge marker/outbox protection; unit test |
| Adjacent offline and group-list regressions | PASS — offline-sync 5/5, group-management 6/6, global-balance isolated pass (see §3) |
| Tier changes take effect on the next request | PASS — `test_admin.py::test_tier_change_takes_effect_on_the_next_request` |

## 5. Deviations and open questions

- “Admin polish” did not include a visual redesign. The dashboard delivered in
  Stage 8D already covers metrics, search, pagination, tiers, preauthorization,
  user deletion and group deletion; this stage adds regression coverage for the
  immediate tier effect and keeps the existing `admin.spec.ts` green.
- Guest preferences are merged as positive signals only. Sending explicit
  `false` values at login would overwrite a star/archive choice made on another
  device before the guest cache was synced. The server now enforces mutual
  exclusion, with archive winning, so the positive-only payload cannot leave
  both flags set. New memberships still default to false on the server.
- `group_ids` is now read-only on `/groups/sync`; explicit claims use
  `local_group_ids`. This is a deliberate behavior change from the Stage 5A
  implicit merge so an authenticated list read cannot resurrect a membership
  removed on another device. Visiting a capability URL still grants membership
  through `recordAccess`.
- Membership ordering is arrival-order LWW, not timestamp ordering. A stale
  `user_group` base version applies and replaces that user's flags; this matches
  the plan wording and is now documented instead of being implied.
- The e2e run still exposes a shared-account auth race: when
  `global-balance.spec.ts` reuses `e2e-creator@example.com` across tests, a
  refresh-token 401 can leave the page signed out. The failing test passes alone;
  the group-list and merge assertions are not involved. Stage 11 leaves the
  shared test account alone rather than changing unrelated auth fixtures.
- Stage 11 keeps the existing behavior where an explicit membership removal
  clears that group's local cache and its recent/star/archive selection keys.
  The server-side group and its financial data are preserved; another device
  that pulls the membership tombstone keeps its cached group data. If “remove”
  should retain the local cache too, that is a separate repository-policy
  change.
- The `test_groups_sync.py` filename follows the plan's verification command.
  The pre-existing `test_group_sync.py` is retained for its Stage 5A coverage.
- The complete Playwright suite was not rerun. Stage 11 and the adjacent
  group-list/global-balance/offline specs were run explicitly.

## 6. Intentionally deferred

- Deployment, performance targets and rollback rehearsal — Stage 12.
- Archiving/removing the Node application — Stage 13.
- A full Playwright run across every remaining spec and optional Background
  Sync deployment work.
