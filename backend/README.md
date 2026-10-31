# pysplit API

FastAPI backend for the split-expenses app. Configuration is read from
environment variables or a local `.env`; see [`.env.example`](.env.example).

## Run locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is at `http://localhost:8000`, with Swagger UI at
`http://localhost:8000/api/docs`. Every API route is under `/api`.

## One public origin with an `/api` proxy

The recommended development setup is a **single browser origin**: the SPA dev
server serves the frontend and proxies `/api/*` to this API. The browser only
ever talks to the frontend origin, so there is no CORS, no cross-site cookie
problem, and no separate frontend URL to configure.

```text
browser ──https──> https://5173.test.example.com
                    ├── /            -> Vite dev server
                    └── /api/*       -> http://127.0.0.1:8000
```

Vite proxy configuration:

```ts
// vite.config.ts
import { defineConfig } from "vite";

export default defineConfig({
  server: {
    host: "127.0.0.1",
    // Required when serving Vite through a custom development hostname.
    allowedHosts: [".test.example.com"],
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
});
```

The SPA should use relative URLs (`/api/...`) and no API base URL:

```dotenv
VITE_API_BASE_URL=/api
```

When the frontend is served over HTTPS, the HTTPS terminator (Tailscale,
Caddy, nginx, etc.) should forward to Vite, and Vite forwards `/api` to the
backend. Configure the API for the public origin:

```dotenv
# The origin the browser uses for both the SPA and /api.
BASE_URL=https://5173.test.example.com

# Not needed with the same-origin /api proxy. Only set it when the SPA and
# API are deliberately on different origins.
# FRONTEND_URL=

TRUST_FORWARDED_HEADERS=true

AUTH_GOOGLE_ID=...
AUTH_GOOGLE_SECRET=...
```

Register this exact redirect URI in the Google Cloud console:

```text
https://5173.test.example.com/api/auth/oauth/google/callback
```

`BASE_URL` is the public origin used to build the OAuth `redirect_uri`. Because
the browser reaches `/api/auth/oauth/google/callback` on that same origin, the
Vite proxy forwards the callback to the backend. The backend then redirects to
the app-relative `return_to` path (for example `/groups`), so the user lands
back on the SPA.

### Frontend login hand-off

The login button must be a **full-page navigation**, not a `fetch`, because the
OAuth code exchange happens at Google and cannot be read by XHR:

```ts
const returnTo = window.location.pathname + window.location.search;
window.location.assign(
  `/api/auth/oauth/google/start?return_to=${encodeURIComponent(returnTo)}`,
);
```

After the callback, restore the session with same-origin requests:

1. `GET /api/auth/me` with `credentials: "include"`; read `csrf_token`.
2. If a refresh cookie exists, `POST /api/auth/refresh` with
   `credentials: "include"` and `X-CSRF-Token: <csrf_token>`. The response
   contains the access token and a rotated `csrf_token`.
3. Send the access token as `Authorization: Bearer <token>` to other API calls.

Cookies are host-only on the single origin. When `BASE_URL` starts with
`https://`, they are marked `Secure` automatically. `TRUST_FORWARDED_HEADERS`
gives correct client IPs for rate limiting when a trusted proxy is in front.

## Optional split frontend/backend origins

If you deliberately run the SPA and API on different origins (for example
`https://5173.test.example.com` and `https://8000.test.example.com`), set both
and allow the frontend origin:

```dotenv
BASE_URL=https://8000.test.example.com
FRONTEND_URL=https://5173.test.example.com
```

`FRONTEND_URL` makes OAuth success/error redirects return to the SPA, adds the
SPA origin to the CORS allowlist, and allows the SPA to pass an absolute
`return_to` URL on its own origin. Use `CORS_ORIGIN_REGEX` if each dev port has
its own subdomain:

```dotenv
CORS_ORIGIN_REGEX=https://\d+\.test\.example\.com
```

The expression is matched against the full origin and is used by both CORS and
the CSRF origin check. If the two origins are unrelated sites, also set
`COOKIE_SAMESITE=none` (HTTPS required).

Point the SPA at the API origin, including the `/api` prefix:

```dotenv
VITE_API_BASE_URL=https://8000.test.example.com/api
```

The frontend sends credentials on API calls, starts OAuth at
`${VITE_API_BASE_URL}/auth/oauth/{provider}/start`, and reads `csrf_token` from
`GET /api/auth/me` and `POST /api/auth/refresh` because a cross-origin SPA
cannot read the API host's CSRF cookie.

## Tests

```bash
.venv/bin/python -m pytest
```


## Production

The deployable stack is the repository-root `compose.yaml` with
`Dockerfile.api` and `Dockerfile.web`. Create the production environment from
`.env.production.example` (not the development `.env.example`), set `BASE_URL`
and a unique `JWT_SECRET`, then run:

```bash
docker compose build && docker compose up -d
```

The API runs Alembic before Uvicorn and uses one worker against SQLite in
`/data`. See `docs/runbook-cutover.md` for the cutover and rollback procedure,
and `docs/performance.md` for the measured budgets.

Operational scripts:

```bash
python scripts/backup.py --database /data/pysplit.db \
  --uploads /data/uploads --output /backups
python scripts/backup_loop.py --once          # reads DATABASE_URL/UPLOAD_DIR
python scripts/restore.py --backup /backups/pysplit-backup-... \
  --database /data/pysplit.db --uploads /data/uploads
python scripts/performance_check.py
```
