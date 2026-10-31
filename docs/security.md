# Security model

Status: current for the M1/M2 server; offline sync is staged (see
`offline-capabilities.md`).
Related: `adr/0003-auth.md`, [`../MIGRATION_PLAN.md`](../MIGRATION_PLAN.md) §2.6,
`api.md`, and `runbook-cutover.md`.

## 1. Capability URLs are intentional and not private

Group-scoped endpoints are deliberately **unauthenticated** so that an existing
shared link keeps working (MIGRATION_PLAN §2.6). That includes group, participant,
expense, receipt and expense-document reads and writes. There are no per-group
ACLs in v1.

Anyone who has a group URL can read the group and can create, edit or delete its
data. This is a link-as-capability model, not privacy. Do not put secrets in
group fields, notes or receipts, and do not treat possession of a URL as proof of
identity. The explicit exceptions are account mutations (group creation and
star/archive membership changes), admin endpoints, and the AI endpoints, which
require a signed-in user. Group-list sync and access recording are optionally
authenticated: they still work anonymously for capability-link use.

The UI and documentation must not imply that shared links are private. See
`adr/0003-auth.md` and [`../MIGRATION_PLAN.md`](../MIGRATION_PLAN.md) §2.8.

## 2. Authentication invariants

- **Mock login is opt-in.** `POST /api/auth/mock-login` exists only when
  `ENABLE_MOCK_LOGIN=true`, and is always `404` when `ENVIRONMENT=production`,
  regardless of the flag. Never enable it on a public deployment.
- **OAuth emails must be verified.** Account linking uses the provider account
  id or a provider email that the provider marks verified. An unverified email
  returns `403` and is never used to auto-link or take over an existing account.
  OAuth state and `return_to` are validated; redirects stay on the origin.
- **Refresh tokens rotate.** The refresh token is an opaque value, hashed at
  rest, delivered in an `HttpOnly` cookie scoped to `/api/auth`, and rotated on
  every refresh. Reuse of an already-rotated token revokes the whole token
  family. Logout revokes the family, not just the presented token.
- **Cookies are `SameSite=Lax` by default.** The refresh cookie is `HttpOnly`;
  the readable `pysplit_csrf` cookie is the double-submit value. Cookies are
  `Secure` in production (or when `BASE_URL` is https). A split SPA/API setup on
  unrelated sites must set `COOKIE_SAMESITE=none` (HTTPS only); sibling
  development subdomains can stay on `Lax`.
- **Cookie mutations are CSRF-protected.** Refresh and logout require a
  same-origin `Origin`/`Referer` and `X-CSRF-Token` matching the CSRF cookie.
  `/api/auth/me` and `/api/auth/refresh` also return the token so a
  cross-origin SPA, which cannot read the API host's cookie, can echo it.
  Bearer-token API calls are not sent automatically by browsers and are not
  subject to this check.
- **Access tokens are memory-only.** The 15-minute access token is held by the
  SPA in memory, never in `localStorage` or IndexedDB. Tier is reloaded from the
  database on every request.
- **Production settings are enforced.** Startup fails when
  `ENVIRONMENT=production` unless `JWT_SECRET` is unique and at least 32
  characters and `BASE_URL` is an absolute `http(s)` URL. `JWT_SECRET` must
  never be the development default.

## 3. Proxy, transport and rate limits

- Terminate TLS in front of the app and keep the public origin in `BASE_URL`.
  This is also the origin used for OAuth redirect URIs and CSRF checks.
- `TRUST_FORWARDED_HEADERS=false` by default. Set it to `true` only when a known
  reverse proxy overwrites `X-Forwarded-Proto`, `X-Forwarded-Host` and
  `X-Forwarded-For`. Enabling it behind an untrusted client lets callers spoof
  the origin and their rate-limit identity. The Compose web tier replaces
  `X-Forwarded-For` with `$remote_addr` rather than appending to a
  client-supplied value. If a CDN or edge proxy is in front of nginx, configure
  `set_real_ip_from`/`real_ip_header` there so `$remote_addr` is the client.
- Rate limits run in-process: authentication per IP and account, AI per caller,
  uploads per caller, and `/api/sync/*` per caller. They return `429` with
  `Retry-After`. The limiter is memory-only, so it is per process and resets on
  restart; a multi-worker deployment needs a shared store.
- CORS is an explicit allowlist; credentials are allowed only for those origins.

## 4. Uploads and AI

- Uploads enforce `MAX_UPLOAD_BYTES`, an allowed content-type list, and
  server-generated storage keys. Receipt image keys are group-scoped
  (`receipts/{group_id}/…`); an image id presented under another group's route
  is rejected. Document reads re-check that the document belongs to the expense
  and group in the route.
- `ENABLE_EXPENSE_DOCUMENTS=false` (the default) makes document upload,
  download and delete return `403`.
- Receipt extraction and category inference require an authenticated bearer
  user (`401` otherwise). AI URLs are restricted to configured storage or the
  app's own upload routes, which limits server-side request forgery.
- AI extraction retries are bounded by `RECEIPT_MAX_ATTEMPTS` (default 3). The
  cap is per uploaded image; exhausted attempts return `409` and require a new
  upload. `ReceiptRead.provider` is a stable public label
  (`openai-compatible`, `google` or `disabled`), never the internal base URL.

## 5. Known limitations

- **REST writes are not in the sync change log.** Only `/api/sync/push` writes
  and server-side recurrence materialization append `SyncChange` rows. A REST
  edit does not appear to clients that only call `/api/sync/pull` until they
  bootstrap or the record is rewritten through sync. REST and sync are not
  interchangeable yet; the unified write path is a Stage 9/C follow-up and is
  not implemented. See `offline-capabilities.md` §2.1.
- **SQLite is single-writer.** Production assumes one Uvicorn worker and a
  local SQLite database in WAL mode with `busy_timeout` (`SQLITE_BUSY_TIMEOUT_MS`,
  default 5000 ms), foreign keys enabled, and short transactions. Multiple
  writers, a network filesystem, or multiple processes can produce lock
  contention and must not be assumed safe. The production entrypoint forces one
  worker.
- **Capability URLs cannot be revoked per user.** Rotating or deleting a group
  is the only way to invalidate the link. There are no private groups.

## 6. Deployment checklist

- [ ] `ENVIRONMENT=production`, a unique `JWT_SECRET` of at least 32 characters,
      and an `http(s)` `BASE_URL` are set through the environment or a secret
      manager — never committed `.env` files or the image.
- [ ] `ENABLE_MOCK_LOGIN=false`; `TRUST_FORWARDED_HEADERS` reflects an actual
      trusted proxy; `COOKIE_SECURE` is not weakened.
- [ ] `.env.production.example` was used for Compose, not the development
      `.env.example`. Compose derives `ENVIRONMENT` from
      `PYSPLIT_ENVIRONMENT` (default `production`) and the host port from
      `COMPOSE_WEB_PORT`, so a copied development file cannot disable the
      production JWT/cookie guards.
- [ ] nginx includes the security-header snippet in every location that sets a
      cache header; `add_header` is not inherited once a location defines one.
- [ ] TLS terminates at the proxy; the public origin matches `BASE_URL` and the
      CORS allowlist; `/api` is proxied, not served from disk.
- [ ] Feature flags (`ENABLE_RECEIPT_EXTRACT`, `ENABLE_RECEIPT_ITEMS`,
      `ENABLE_CATEGORY_EXTRACT`, `ENABLE_EXPENSE_DOCUMENTS`) are off unless
      intended, and AI credentials are scoped to the provider.
- [ ] Backups use `scripts/backup.py` (SQLite online backup API) — never a
      raw copy of a live WAL file. Store backups off-host, record checksums, and
      test a restore with `scripts/restore.py --dry-run` and one real restore.
      See `runbook-cutover.md` §3.
- [ ] `compose.yaml` publishes only the web tier; the API stays on the internal
      network. nginx sets `Cache-Control: no-store` for `/api` and never caches
      the service worker or build contract.
- [ ] Logs are structured (`LOG_FORMAT=json`) and contain request ids but never
      access tokens, refresh cookies, AI keys or full request bodies.
- [ ] Monitor auth refresh/OAuth failures, `429`/`5xx` rates, SQLite `busy`
      errors, upload failures and AI `FAILED` receipts.
- [ ] Rotate secrets and provider credentials after exposure, and review the
      dependency-audit jobs in CI.

## 7. Reporting a security issue

Report suspected vulnerabilities to the repository owner or deployment operator
through a private channel. Do not open a public issue with exploit details,
group links, tokens or personal data. Include the affected endpoint, a minimal
reproduction, and whether the capability-URL model or an authenticated feature
is involved.
