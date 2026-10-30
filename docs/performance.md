# Performance targets and measurements

Status: Stage 12 targets implemented and measured on the development sandbox.
Re-measure on staging-sized data before cutover.

## Targets

| Area | Target | Check |
|---|---|---|
| First expense page (10,000 expenses) | p95 < 300 ms | `backend/scripts/performance_check.py` |
| 50-operation sync push | < 500 ms | `backend/scripts/performance_check.py` |
| Bootstrap of a 1,000-expense group | < 1 s | `backend/scripts/performance_check.py` |
| Initial JavaScript | < 300 KB gzip | `frontend/scripts/check-bundle-size.mjs` |
| Offline boot (mid-range phone) | < 2 s | Playwright/Lighthouse on staging |
| PWA installable | Lighthouse PWA pass | `e2e/pwa.spec.ts` + Lighthouse |

## Commands

```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/performance_check.py

cd ../frontend
npm run build
npm run check:bundle
```

The backend script seeds a disposable database with 10,000 + 1,000 expenses,
runs 25 expense-list requests, one 50-operation sync push, and one 1,000-expense
bootstrap. It exits nonzero if a budget is missed. Numbers include FastAPI
serialization through `TestClient` but exclude network latency. The bundle
script counts the entry module and every `modulepreload` chunk listed in
`dist/index.html` after gzip; lazy route chunks are not part of first render.

## Stage 12 measurement (2026-10-30, sandbox)

```text
Expense page p95: 6.78 ms (budget 300 ms)
50-op sync push:  117.24 ms (budget 500 ms)
Bootstrap 1,000:  131.47 ms (budget 1000 ms)
Initial JS:       198,915 bytes gzip = 194.3 KiB (budget 307,200 bytes)
```

These are sandbox figures with a local SQLite file, not production latency.
Record a fresh run on the staging copy in the cutover log.
