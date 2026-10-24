# ADR 0001 — Target stack

Status: Accepted
Date: 2026-10-24
Related: ADR 0000 decision 1

## Context

The reference fork is a Next.js 16 / tRPC 11 / Prisma application with a
SQLite database. It must be replaced by a Python-first stack without changing
the user-visible product: shared group URLs, expense semantics, balances,
statistics, receipts, authentication tiers and admin tools all stay.

The migration will be executed in bounded stages, so the stack must support
incremental delivery and a stable repository boundary before offline support
is added.

## Decision

| Layer | Choice |
|---|---|
| API | FastAPI + Uvicorn |
| Persistence | SQLModel (SQLAlchemy 2) + Alembic |
| Validation | Pydantic v2 at the HTTP boundary |
| Backend tests | pytest, pytest-xdist, in-memory SQLite + `StaticPool` |
| Backend quality | Ruff, coverage, `pip-audit` |
| Frontend | React + Vite, plain `.jsx`, `checkJs` |
| Frontend forms | zod |
| Frontend data | native `fetch` in one `services/api.js`; feature hooks; repository boundary |
| Offline | Dexie/IndexedDB repository + outbox |
| PWA | `vite-plugin-pwa` / Workbox |
| Frontend tests | Vitest + Testing Library + jsdom; Playwright |
| Frontend quality | oxlint, `tsc -p jsconfig.json`, `npm audit` |
| i18n | i18next + react-i18next, ported locale files |
| Deployment | Docker Compose: `api` + `web` (nginx) |

The backend is layered strictly:

```
api/ (HTTP only) → services/ (transactions, business logic) → models/ (SQLModel)
                         ↘ utils/ (pure domain functions, no I/O)
```

Routers never import SQLAlchemy models or touch a session directly. Pure
utilities never import HTTP, database, storage or configuration modules. These
rules are enforced by `scripts/check_architecture.py` from Stage 8A onward and
by review before that.

## Consequences

- Python owns canonical validation, IDs, timestamps, activity logging,
  recurrence materialization and AI calls.
- The SPA can run entirely from IndexedDB later without rewriting components,
  because components and hooks depend on the repository contract.
- SQLite is a v1 constraint, not an architectural one: SQLModel types and
  Alembic migrations keep a later PostgreSQL move possible.
- Plain `.jsx` trades compile-time types for a simpler build; `checkJs`,
  zod schemas, contract tests and shared fixtures must catch what TypeScript
  would have caught.

## Rejected alternatives

- **Keep Next.js and add a Python sidecar.** Rejected: two runtimes, two auth
  systems, and no retirement path.
- **GraphQL instead of REST.** Rejected: the plan fixes REST conventions and
  the repository boundary already isolates the transport.
- **PostgreSQL in v1.** Rejected: adds operational work; the fork ships SQLite
  and the expected scale fits one node.
- **TypeScript SPA.** Rejected by decision 1; can be revisited only by a new
  ADR before Stage 8A.
- **react-query/axios.** Rejected: the plan requires one fetch client and a
  repository boundary; extra data libraries would duplicate cache semantics.
