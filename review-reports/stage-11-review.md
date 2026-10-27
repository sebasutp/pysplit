# Stage 11 review — authenticated group sync and admin polish

**Scope:** uncommitted working tree vs `HEAD` `ced6850` (`Stage 10`): 15 files, ~1,048 insertions, covering the Stage 11 group-claim/merge, membership sync, tests, docs and the two check scripts. Read-only review of application code; only throwaway probes under the sandbox home were used.

**Verdict: NEEDS REFACTOR.** The gate commands are green, but the green tests do not exercise the two-device cases the gate names. Cross-device removal is still undone by the other device's stale group list, and a guest archive can clobber an existing star and leave both flags set. No confirmed financial data loss was reproduced; the pruning risk in H4 remains a code-level risk.

> Correction to the first draft: the same-device UI removal path itself works for starred and archived groups. The stale-star/archive hypothesis was tested and refuted; the confirmed removal bug is (a) another device reloading after a UI removal, and (b) a direct `repository.groups.removeMembership` call with a stale recent list. Details in H1.

## Commands actually run

| Command | Result |
|---|---|
| `cd frontend && npm test -- --run` | **40 files / 143 tests passed** (matches report) |
| `cd frontend && npm run lint` | 0 warnings, 0 errors |
| `cd frontend && npm run typecheck` | clean |
| `cd frontend && npm run build` | success; PWA 90 precache entries / 1550.70 KiB (report says 1550.61) |
| `cd backend && PYTHONPATH=. .venv/bin/pytest -q tests/test_admin.py tests/test_groups_sync.py` | **19 passed** |
| `cd backend && PYTHONPATH=. .venv/bin/pytest -q -n auto` | **321 passed, 2 skipped**; coverage 92.83% (matches report) |
| `python3 scripts/check_architecture.py` | OK |
| `python3 scripts/check_parity_matrix.py` | OK, 123 features; `spliit/` empty => manifest fallback (see M2) |
| `npx playwright test e2e/group-sync.spec.ts e2e/admin.spec.ts --workers=1` | **5 passed (10.3s)** against a fresh `./dev` stack |
| `npx playwright test e2e/group-management.spec.ts e2e/global-balance.spec.ts --workers=1` | **9 passed (44.0s)** |
| `npx playwright test e2e/offline-sync.spec.ts --workers=1` | **5 passed (39.5s)** |
| Chromium: same-device UI remove of a **starred** group, then reload | **not reproduced**: server scope has no group before and after reload; stale localStorage `starredGroups` remains but is not sent as a `groupId` |
| Chromium: same-device UI remove of an **archived** group, then reload | **not reproduced**: same result; stale localStorage `archivedGroups` remains, no membership re-created |
| Chromium: same-device direct `repository.groups.removeMembership` (without `deleteRecentGroup`), then refresh/reload | **reproduced**: server membership deleted `20:35:12.982`, re-created `20:35:12.998` (16 ms later) by the same page's list load |
| Chromium: B UI-removes membership, A (same account, different device) reloads | **reproduced**: B's delete applied `20:35:15.641`; A's reload re-created the single membership row `20:35:16.766` (1.1 s later) |
| Chromium: A stars, B guest-archives then logs into A's account | server membership ended **`is_starred=1, is_archived=1`**; B's claim op payload was `is_starred=false, is_archived=true` (see H2) |
| Parity probe in a temp copy: empty `spliit/` + `--write-reference-manifest` | rewrote the manifest to 4 header lines and printed **OK: 0 pages/0 procedures/0 Jest/0 Playwright** (see M2) |

**Not run:** the complete Playwright suite, Lighthouse/performance checks, backup/restore, or a real OAuth (non-mock) login. E2E used a fresh local database (`DATA_DIR` outside the repo).

## High

### H1. A removal on one device is undone by another device's next list load (or by a direct `removeMembership` caller on the same device)

This is narrower than the first draft. The **UI** remove path is `useGroups.remove`, which calls `deleteRecentGroup(groupId)` before `repository.groups.removeMembership(groupId)` (`frontend/src/hooks/useGroups.js:186-202`). I tested that path in Chromium for both a starred and an archived group: the membership stayed deleted after the removing device reloaded. It also leaves the removed ID in localStorage `starredGroups`/`archivedGroups` (because `remove` does not call `unstarGroup`/`unarchiveGroup`), but those sets are not sent as `groupIds`, so they do **not** re-create the membership. That stale-localStorage hypothesis is refuted.

What does reproduce:

1. **Same device, direct repository call.** `repository.groups.removeMembership(groupId)` (`frontend/src/services/repository/local.js:1250-1276`) deletes the local rows but does not remove the ID from localStorage `recentGroups`. The next `groups.sync`/`useGroups` load sends that stale recent ID (`frontend/src/hooks/useGroups.js:51-63`), the server treats every `groupIds` entry as an implicit claim (`backend/app/services/groups.py:572-593`), and the membership is re-created. Probe: B called `removeMembership` while still on `/groups`; the server delete was applied at `20:35:12.982`, and the same page's refresh/`groups.sync` re-created it at `20:35:12.998` (16 ms). The current UI has no direct caller, so this is a repository-contract bug, but it is real for any future caller and for tests.
2. **Cross-device UI removal.** B removes through `useGroups.remove` (server row gone at `20:35:15.641`), then A reloads `/groups`. A still has the group in its localStorage recent list; `useGroups` sends it as a `groupId`; the server re-creates the single `user_groups` row at `20:35:16.766` (1.1 s later). A and B are the same account; `UserGroup` is keyed by `(user_id, group_id)`, so B's delete removed A's membership too. This is not "A is still a member"; the row is absent after B's delete and is re-created by A's stale list read. This is the user-visible two-device failure.

The new `pysplit:refresh` listener (`useGroups.js:119-129`) makes the stale claim fire on every sync broadcast, and `cacheSyncResult` only prunes Dexie/metadata recent (`local.js:424-452`), not the localStorage selection keys read by `useGroups`.

**Fix:** make `removeMembership` itself clear the recent/star/archive entries (so the repository contract is safe for every caller), and reconcile localStorage from the authenticated scope response. Better, separate "claim a group" from "list the account scope" so a list read cannot create memberships. Add a two-device e2e: B removes via the UI, A reloads/syncs, assert the group stays gone and no new `user_groups` row appears.

### H2. The guest merge sends explicit `false` for the other flag and clobbers a star made on another device

`prepareGuestMerge` comments that guest preferences are "only a positive signal" (`frontend/src/services/repository/local.js:213-216`), but for a guest device the local membership `existing` is null, so the code sends `{is_archived:true, is_starred:false}` or `{is_starred:true, is_archived:false}` (`local.js:217-231`). The server applies that payload to an existing membership (`backend/app/services/sync.py:713-719`), and the `/groups/sync` claim path is positive-only per flag without enforcing star/archive exclusivity (`backend/app/services/groups.py:576-592`).

Reproduction: A stars the group; B visits as a guest and archives it; B logs into A's account. B's claim op is recorded with `is_archived=true, is_starred=false` (version 3), overwriting A's star. A's next list load sends its stale `starredGroups` ID, so the server sets the star back while leaving archive true; the resulting DB row is `is_starred=1, is_archived=1`. B saw `star=false, archived=true`; A saw both true.

The report's §5 claim "Guest preferences are merged as positive signals only" is false in the code, and the star/archive gate is not met: a guest archive can erase another device's newer star, then the other device can re-add the star and produce an invalid state.

**Fix:** for an unknown local membership send only the positive flag (omit the other key); enforce mutual exclusion server-side (`archived` implies unstarred, or use a single `preference` value); add a backend test with an existing starred membership plus an archived guest claim, and a two-device e2e that asserts one flag remains set.

### H3. The gate tests do not exercise the merge, and the PASS table overstates them

- `backend/tests/test_groups_sync.py:40-62` is not a two-device test: both "devices" are two `/api/groups/sync` calls in one test. It would pass if the sync push/pull engine, change feed, or second-device propagation were broken.
- `frontend/e2e/group-sync.spec.ts:105-156` claims a guest group "on login" but, after login, navigates to `/groups`; `useGroups` sends the group's recent ID and the server claims it (`useGroups.js:57-62`, `groups.py:572-593`). The test would pass if `prepareGuestMerge`, the marker, and the outbox were deleted. It also asserts only group/membership counts, not that the guest expenses/participants survived.
- There is no e2e for removal on B + observation on A (H1), no guest-archive + existing-star case (H2), and no test for the marker/prune race (H4). The unit mock in `group-sync.test.js:130-152` returns groups without `participants` or `user_group`; it does not exercise the real response shape or the prune path.
- The report's PASS rows for "remove without deleting data", "star/archive LWW", and "guest group claimed on login" are therefore unsupported even though the suite is green.

**Fix:** add failing-first tests for the four required two-device scenarios using the real sync engine (push/pull), not direct `/groups/sync` polling; assert data (an expense) survives the guest claim; add the removal-on-B case and the star/archive case.

### H4. `cacheSyncResult` prunes groups without consulting the pending merge marker, deleting queued claims/outbox rows

`cacheSyncResult` deletes every authenticated local group missing from the response unless it has a pending **group** create (`local.js:349-364, 424-452`). `prepareGuestMerge` enqueues `user_group` creates and a marker, not group creates, so those IDs are not protected. `deleteLocalGroup` then deletes the group's expenses, participants and **outbox rows** (`db.js:732-740`), including the queued claim and any offline expense.

`runSync` also calls `reconcileGroupScope()` unconditionally after `pushPending()` (`sync.js:746-752`), even when push returned errors/pending rows. If a normal list sync (mount, `pysplit:refresh`, or a response omitting a marker group) runs before the claim is acknowledged, the local group and its unsynced writes are deleted; the marker only carries group IDs, so it cannot restore local-only expense data. This remains a code-level risk; I did not reproduce a permanent loss in the browser probes.

**Fix:** protect `pending_group_merge.group_ids` and pending `user_group` creates from pruning; do not delete outbox rows for a group during a scope refresh; only prune after the merge is acknowledged, or defer deletion until the group is confirmed gone server-side. Add a test with a guest group, an offline expense, and a list response that does not yet include the group.

## Medium

### M1. "LWW" is an arrival-order policy that is not documented as such; `base_version`/`client_time` are not compared

`_apply_user_group` only checks that `base_version` is present, never compares it to the stored version, and ignores `client_time` (`backend/app/services/sync.py:367-370,694-695,713-722`). The Stage 11 report explicitly defines LWW as "a stale `user_group` base version applies", so arrival-order-wins is a legitimate policy under the plan as written; this is not, by itself, a plan violation. The objective issue is that it is not named as arrival-order in the docs, and it leaves a lost-update window: an old offline toggle reconnecting after a newer toggle silently overwrites it. The new test enshrines stale-apply (`test_groups_sync.py:94-111`).

**Fix:** document the policy explicitly, or compare `base_version`/`client_time` if true last-write-by-time is intended. Add a test that pins the chosen ordering.

### M2. `check_parity_matrix.py` treats an empty `spliit/` as absent but the write path still accepts it and erases the manifest

The new `reference_present = REFERENCE.is_dir() and any(REFERENCE.iterdir())` (`scripts/check_parity_matrix.py:129-159`) silently falls back to `docs/reference-manifest.txt` when a checkout mounted an empty reference directory. That hides a partially initialized reference tree, and the fallback is inconsistent with `--write-reference-manifest`, which still checks only `REFERENCE.exists()` (`:270-275`). In a temp copy with an empty `spliit/`, `--write-reference-manifest` overwrote the 90-line committed manifest with the four header lines and then printed `OK: 123 features; 0 pages...` with exit 0.

**Fix:** use the same `reference_present` predicate in `main()`; refuse `--write-reference-manifest` when the tree has no expected source; if a sandbox fallback is required, make it explicit (`--allow-missing-reference`).

### M3. Docs/report overclaim the merge ordering and preference semantics

- `docs/repository-contract.md:160` says the marker is reconciled "after the queue drains"; `sync.js:746-752` reconciles regardless of push errors/pending rows.
- `docs/offline-capabilities.md:154-155` says the claim "is pushed before the scope is reconciled"; if `/sync/push` fails, the scope can be fetched first.
- `docs/stage-11-report.md` §5 says guest preferences are positive-only (false, H2), and the gate table marks removal/LWW PASS without the two-device tests above.
- "Admin polish" is claimed as PASS but no admin UI changed in this stage; the report itself admits it is existing Stage 8D work.

## Recommendation

1. Fix H1 first: make `removeMembership` clear the local recent/star/archive keys, and reconcile those keys from the authenticated scope response so a list read cannot re-create a removed membership. Add the B-removes/A-syncs e2e.
2. Fix H2: send positive-only preference for unknown memberships, enforce mutual exclusion server-side, and add the existing-star + guest-archive test.
3. Make pruning merge-aware (H4); never delete an outbox claim or offline expense during a list refresh.
4. Replace the direct-endpoint "two-device" tests with push/pull or real browser contexts that would fail with the merge code removed; then correct the report's PASS table.
5. Document the LWW ordering choice (M1), fix the empty-reference guard (M2), and correct the docs (M3).
