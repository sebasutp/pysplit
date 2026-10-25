# pysplit

Self-hosted expense splitting app. The backend is FastAPI + SQLModel with
SQLite; the frontend is React + Vite. This repository is a staged rewrite of
the existing Spliit app. The backend routes are implemented, and
`docs/parity-matrix.yml` tracks their coverage against the reference app.

## Requirements

- Python 3.12
- Node.js 22 or newer (CI uses Node 24)
- `make`

## Start the app

Install dependencies once:

```bash
make install
```

Start the API and the frontend together:

```bash
./dev
```

`./dev` applies any pending Alembic migrations to the development database
before starting the API, so a checkout with newer migrations does not need a
manual `alembic upgrade head`.

Then open <http://127.0.0.1:5173>.

You only need that one port. The backend binds to `127.0.0.1` and the browser
talks to it through Vite's `/api` proxy:

- App: <http://127.0.0.1:5173>
- Health check: <http://127.0.0.1:5173/api/health>
- API docs: <http://127.0.0.1:5173/api/docs>

Development data is stored in `data/dev/pysplit.db`.

### Configure with `.env`

`./dev` loads `./.env` at the repository root. Start from the template:

```bash
cp .env.example .env
```

The defaults work as-is for local development. For an HTTPS domain behind
Caddy/Tailscale, edit these values (and add your Google credentials):

```dotenv
WEB_HOST=5172.test.domain.app
WEB_PORT=5172
PUBLIC_ORIGIN=https://5172.test.domain.app
AUTH_GOOGLE_ID=...
AUTH_GOOGLE_SECRET=...
```

Then just run:

```bash
./dev
```

Variables already exported in your shell override `.env`, so a one-off
`WEB_PORT=5180 ./dev` still works. Set `ENV_FILE=/path/to/file` to load a
different dotenv file.

### Access it from another machine or Tailscale

`WEB_HOST` is the only hostname setting. Set it to the name clients use:

```bash
WEB_HOST=myhost.tailnet.ts.net ./dev
```

Vite then accepts that hostname and listens on all interfaces. Keep using a
single port:

```text
http://myhost.tailnet.ts.net:5173
```

Useful overrides:

| Variable | Default | Purpose |
| --- | --- | --- |
| `WEB_HOST` | `127.0.0.1` | Hostname used in the browser URL and Vite host checks |
| `WEB_PORT` | `5173` | Frontend/development port |
| `PUBLIC_ORIGIN` | `http://$WEB_HOST:$WEB_PORT` | Exact browser origin; use an HTTPS URL behind a TLS proxy |
| `API_PORT` | `8000` | Internal API port; the default falls forward if busy |
| `DATA_DIR` | `data/dev` | Directory for the local SQLite database |
| `ENV_FILE` | `./.env` | Dotenv file loaded by `./dev`; shell variables take precedence |

### Google login behind an HTTPS domain

The browser keeps talking to a single origin. If a reverse proxy (Tailscale
Serve, Caddy, nginx, a tunnel) terminates TLS and forwards to Vite, set
`PUBLIC_ORIGIN` to the address the browser opens:

```bash
WEB_HOST=app.example.com PUBLIC_ORIGIN=https://app.example.com ./dev
```

Or put those values and your Google credentials in `.env` and run `./dev`.

`PUBLIC_ORIGIN` becomes the API's `BASE_URL`, so it is used for the OAuth
redirect URI, CSRF origin checks and `Secure` cookies. Vite still listens on
`WEB_PORT`; the proxy forwards to it. Register this exact URI in the Google
Cloud console:

```text
https://app.example.com/api/auth/oauth/google/callback
```

`WEB_HOST` must be the same hostname as `PUBLIC_ORIGIN` so Vite accepts the
proxied `Host` header. The `/api` proxy stays on the same origin, so there is
no CORS or cross-site cookie configuration to manage.

## Tests and checks

Run everything:

```bash
make test
```

Run only one side:

```bash
# Backend (pytest; coverage threshold is 80%)
cd backend
PYTHONPATH=. .venv/bin/pytest -n auto

# One backend file
PYTHONPATH=. .venv/bin/pytest tests/test_health.py -q

# Frontend (Vitest, single run)
cd frontend
npm test -- --run

# Frontend watch mode
npm test

# Frontend coverage with the enforced v8 thresholds
npm run test:coverage
```

Other useful commands:

```bash
make lint        # Ruff + oxlint, including format check
make typecheck   # TypeScript checking for the JS frontend
make build       # Production frontend build into frontend/dist
make parity      # Check parity against the committed reference inventory
make test-coverage  # Frontend coverage with enforced thresholds
make clean       # Remove caches, coverage and build output
```

CI (`.github/workflows/ci.yml`) runs these checks, the parity and architecture
checks, and the Playwright end-to-end suite after starting the API and Vite dev
server. Playwright is a separate CI job; `make test` does not run it.

The parity check validates `docs/parity-matrix.yml` and uses the committed
`docs/reference-manifest.txt` for the list of reference files. When the
read-only `spliit/` oracle is mounted locally, the checker uses the live tree
instead and fails if the manifest is stale. Regenerate it after the reference
tree changes:

```bash
python scripts/check_parity_matrix.py --write-reference-manifest
```

## Run services separately

Normally use `./dev`, but each side can run on its own.

Backend:

```bash
cd backend
cp ../.env.example .env       # canonical template; edit DATABASE_URL/CORS as needed
PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The repository-root `.env.example` is the canonical template; `backend/.env.example`
just points to it. For a backend-only run, copy it into `backend/.env` as shown
above (the `VITE_*` keys are ignored by the API).

Frontend:

```bash
cd frontend
WEB_HOST=127.0.0.1 VITE_API_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

The frontend calls same-origin `/api` by default; Vite forwards it to
`VITE_API_PROXY_TARGET`. The proxy preserves the browser-facing `Host` header
so OAuth redirect URIs and CSRF checks match the URL you opened. Set
`VITE_API_PROXY_SECURE=false` only when the proxy target is HTTPS with a
self-signed certificate, and `VITE_API_PROXY_CHANGE_ORIGIN=true` only when a
remote target is virtual-hosted and requires its own `Host` header.

A split origin (frontend and API on different hosts) is also supported. Set
`VITE_API_BASE_URL` to the backend origin including `/api`, plus `BASE_URL`,
`FRONTEND_URL` and the CORS allowlist on the API:

```bash
cd frontend
VITE_API_BASE_URL=https://api.example.com/api npm run dev
```

Only `VITE_*` variables are exposed to browser code. Prefer the same-origin
proxy unless you specifically need separate hosts.

## Project layout

```text
backend/app/api/        HTTP routers
backend/app/services/   business logic
backend/app/models/     SQLModel models
backend/app/core/       settings and database setup
backend/tests/          pytest suite
frontend/src/           React app and the single HTTP client in services/api.js
docs/                   API contract, security model, decisions and stage reports
dev                     development launcher for API + Vite
```

Further reading: `docs/api.md`, `docs/repository-contract.md`,
`docs/security.md`, and the ADRs in `docs/adr/`.
