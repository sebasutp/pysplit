# pysplit

Self-hosted expense splitting app. The backend is FastAPI + SQLModel with
SQLite; the frontend is React + Vite. This repository is a staged rewrite of
the existing Spliit app; current routes are still placeholders.

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

Then open <http://127.0.0.1:5173>.

You only need that one port. The backend binds to `127.0.0.1` and the browser
talks to it through Vite's `/api` proxy:

- App: <http://127.0.0.1:5173>
- Health check: <http://127.0.0.1:5173/api/health>
- API docs: <http://127.0.0.1:5173/api/docs>

Development data is stored in `data/dev/pysplit.db`.

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
| `API_PORT` | `8000` | Internal API port; the default falls forward if busy |
| `DATA_DIR` | `data/dev` | Directory for the local SQLite database |

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
```

Other useful commands:

```bash
make lint        # Ruff + oxlint, including format check
make typecheck   # TypeScript checking for the JS frontend
make build       # Production frontend build into frontend/dist
make parity      # Check parity against the committed reference inventory
make clean       # Remove caches, coverage and build output
```

These are the same checks CI runs (`.github/workflows/ci.yml`).

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
cp .env.example .env          # optional; edit DATABASE_URL/CORS as needed
PYTHONPATH=. .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```bash
cd frontend
WEB_HOST=127.0.0.1 VITE_API_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

The frontend always calls same-origin `/api` in development. Do not point
`VITE_API_BASE_URL` at the backend port; that bypasses the proxy and reintroduces
CORS/direct-port access. Only `VITE_*` variables are exposed to browser code.

## Project layout

```text
backend/app/api/        HTTP routers
backend/app/services/   business logic
backend/app/models/     SQLModel models
backend/app/core/       settings and database setup
backend/tests/          pytest suite
frontend/src/           React app and the single HTTP client in services/api.js
docs/                   API contract, decisions and stage reports
dev                     development launcher for API + Vite
```

Further reading: `docs/api.md`, `docs/repository-contract.md`, and the ADRs in
`docs/adr/`.
