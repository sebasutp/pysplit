# Stage 4 report — authentication, tiers, OAuth, admin API

Date: 2026-10-24
Stage: 4

## Outcome

The backend now issues short-lived HS256 access tokens and rotating, hashed
refresh tokens, enforces the three-tier matrix from the database on every
request, supports Google/GitHub OAuth with state and same-origin redirect
validation, and exposes the complete admin API plus an admin bootstrap CLI.
Authentication endpoints are rate limited by IP and, where known, by account.

No endpoint trusts a tier from the token. `GET /api/auth/me` returns `null` for
missing, malformed or expired tokens; protected endpoints return `401`/`403`.
All shared-group endpoints remain unauthenticated, preserving capability URLs.

## Files added or changed

### Core

- `backend/app/core/security.py` — JWT creation/verification, refresh-token
  generation and SHA-256 hashing, constant-time comparisons, CSRF/state
  generators.
- `backend/app/core/oauth.py` — Google/GitHub authorization URLs, token
  exchange, profile retrieval, optional injected HTTP client for tests.
- `backend/app/core/limits.py` — thread-safe sliding-window limiter shared by
  auth endpoints, keyed by IP and account.
- `backend/app/core/enums.py` — `UserTier`, tier normalisation and
  group-creation capability.
- `backend/app/core/ids.py` — prefixed UUIDv4 identifiers for new rows.
- `backend/app/core/validation.py` — email normalisation and same-origin
  `return_to` validation.
- `backend/app/core/config.py` — token TTLs, cookie names/security, OAuth
  credentials, `BASE_URL`, rate limits, and production rejection of a missing
  or development `JWT_SECRET`.

### Services

- `backend/app/services/auth.py` — session issuance, refresh rotation with
  reuse detection/family revocation, logout revocation, OAuth account linking
  (account ID first, then case-insensitive email), development mock login.
- `backend/app/services/admin.py` — metrics, user search/filter/pagination,
  preauthorization, tier changes, user/group deletion, group search with counts.
- `backend/app/services/errors.py` — expected service errors.

### HTTP

- `backend/app/api/auth.py` — `me`, OAuth start/callback, refresh, logout and
  development mock login. Sets `HttpOnly` refresh/state cookies, the readable
  `pysplit_csrf` double-submit cookie, and validates `Origin`/`Referer`.
- `backend/app/api/admin.py` — admin endpoints with `AdminUser` dependency.
- `backend/app/api/deps.py` — optional/current user plus
  `GroupCreatorUser`/`AdminUser` dependencies.
- `backend/app/schemas/auth.py`, `backend/app/schemas/admin.py` — request and
  response contracts.
- `backend/app/main.py` — registers auth and admin routers under `/api`.

### CLI and configuration

- `backend/app/scripts/make_admin.py` — `python -m app.scripts.make_admin`
  promotes an existing email or creates a pre-authorized admin.
- `backend/requirements.txt` — adds `httpx` (already present in the approved
  development/test stack) for OAuth runtime calls.
- `backend/.env.example`, `.env.example` — auth, OAuth, cookie and limiter
  settings.
- `dev` — defaults `BASE_URL` to the public Vite origin so OAuth redirect URIs
  and CSRF origin checks do not use Vite's internal proxy target.
- `docs/api.md` — documents CSRF/origin requirements and admin list shapes.

### Tests

- `backend/tests/test_auth.py` — token tampering/expiry, rotation, reuse
  (service and HTTP), CSRF/origin rejection, cookie attributes, OAuth start,
  callback, state mismatch, open redirects, email linking, provider discovery
  (including `/api/auth/me`), mock transports for Google/GitHub, dev-only mock
  login, IP and account rate limiting.
- `backend/tests/test_admin.py` — metrics, user filtering/pagination,
  preauthorization, tier updates, deletion cascades, group listing/deletion,
  admin matrix, bootstrap CLI.
- `backend/tests/test_rbac.py` — guest/sync/creator/admin matrix for creator
  and admin dependencies, invalid/expired tokens, missing users, unknown tiers,
  immediate tier changes.
- `backend/tests/test_config.py` — production secret and provider discovery
  configuration.
- `backend/tests/conftest.py` — settings-override client factory and limiter
  reset.
- `backend/tests/helpers.py` — user/token/CSRF fixtures shared by the suites.

## Verification commands and output

### Stage tests

```bash
$ cd backend
$ PYTHONPATH=. .venv/bin/pytest tests/test_auth.py tests/test_admin.py tests/test_rbac.py -n auto
63 passed, 25 warnings in 4.75s
TOTAL 1472 statements, 108 missed, 93%
Required test coverage of 80% reached. Total coverage: 92.66%
```

### Full backend suite

```bash
$ PYTHONPATH=. .venv/bin/pytest -n auto
125 passed, 25 warnings in 7.21s
TOTAL 1472 statements, 89 missed, 94%
Required test coverage of 80% reached. Total coverage: 93.95%
```

### Lint and formatting

```bash
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
69 files already formatted
```

### Schema check (no migration required)

```bash
$ DATABASE_URL=sqlite:////tmp/stage4-alembic.db .venv-work/bin/alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_core_schema ...
INFO  [alembic.runtime.migration] Running upgrade 0001_core_schema -> 0002_receipts_schema ...
INFO  [alembic.runtime.migration] Running upgrade 0002_receipts_schema -> 0003_sync_and_auth_schema ...

$ DATABASE_URL=sqlite:////tmp/stage4-alembic.db .venv-work/bin/alembic check
No new upgrade operations detected.
```

### Admin bootstrap

`/tmp/new.db` was the Stage 2 imported database.

```bash
$ PYTHONPATH=. .venv-work/bin/python -m app.scripts.make_admin \
    --email test@example.com --db /tmp/new.db
Created pre-authorized admin: test@example.com (tier=admin)

$ PYTHONPATH=. .venv-work/bin/python -m app.scripts.make_admin \
    --email test@example.com --db /tmp/new.db
Promoted user: test@example.com (tier=admin)
exit=0
```

### Production secret guard

```bash
$ ENVIRONMENT=production PYTHONPATH=. .venv-work/bin/python \
    -c "from app.core.config import Settings; Settings(_env_file=None)"
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
  Value error, JWT_SECRET must be set to a unique value in production
```

### Parity matrix

```bash
$ backend/.venv-work/bin/python scripts/check_parity_matrix.py
OK: 111 features; 14 pages, 28 procedure files, 30 Jest suites,
14 Playwright specs all mapped.
```

## Gate checklist

| Gate item | Status |
|---|---|
| Tier matrix enforced (`sync_users` cannot create; only `admin` administers) | Pass |
| Admin endpoints return 401 anonymous and 403 for non-admin tiers | Pass |
| No protected endpoint accepts a tampered, expired or orphaned token | Pass |
| `/api/auth/me` returns `null` for invalid tokens | Pass |
| Refresh token rotation issues a new token and cookie | Pass |
| Reuse of a rotated token revokes the family and returns 401 | Pass |
| CSRF header/cookie and same-origin checks reject cookie mutations | Pass |
| OAuth state mismatch is rejected | Pass |
| OAuth `return_to` cannot leave the origin | Pass |
| OAuth accounts link by provider account ID or email | Pass |
| Provider discovery reflects configured credentials | Pass |
| Admin bootstrap creates or promotes an administrator | Pass |
| Production refuses the development JWT secret | Pass |
| Auth rate limiting returns 429 with `Retry-After` | Pass |
| Full backend suite, lint and format are green | Pass |

## Deviations and open questions

1. **Venv invocation.** In this sandbox `backend/.venv/bin/python` is a symlink
   whose resolved interpreter loses `.venv-work` site-packages, while
   `.venv/bin/pytest` works through its shebang. Module invocations in this
   report therefore use `.venv-work/bin/python`; the application itself is
   unchanged. This is a sandbox environment artefact, not a code issue.
2. **`httpx` moved to runtime requirements.** OAuth needs an HTTP client. It was
   already in `requirements-dev.txt` and is part of the approved test stack; no
   new library family was introduced.
3. **No new migration.** The Stage 2 `refresh_tokens` table already has
   `revoked_at` and `replaced_by_id`, which are sufficient to detect reuse and
   walk/revoke a rotation family. No schema change was needed.
4. **Mock login included.** `docs/api.md` and the parity matrix require
   `POST /api/auth/mock-login` for Playwright helpers; it returns 404 in
   production.
5. **CSRF cookie.** The contract required a CSRF header; the implementation uses
   a readable `pysplit_csrf` cookie echoed in `X-CSRF-Token` (double submit)
   plus an `Origin`/`Referer` check, matching ADR 0003.
6. **`dev` sets `BASE_URL`.** Without it, Vite's `changeOrigin` proxy would make
   OAuth redirect URIs point at the internal API port. Production must set
   `BASE_URL` explicitly.

## Deferred to later stages

- Frontend auth repository methods, access-token memory storage, CSRF header
  plumbing and login dialog: Stage 8A.
- Admin dashboard UI: Stage 8D.
- Real provider OAuth smoke test: requires Google/GitHub credentials; exchange
  and profile parsing are covered with mocked transports.
- Authenticated group synchronization and `UserGroup` merge endpoints:
  Stage 5A/11.
- Shared rate limiting across multiple API processes: v1 runs one Uvicorn
  worker (plan §12); the limiter is in-process by design.
