# ADR 0000 — Decision register (plan §8)

Status: **Accepted**
Date: 2026-10-24
Supersedes: the open questions in `MIGRATION_PLAN.md` §8

The migration plan proposed recommended defaults for eight decisions. The
product owner instructed this session to implement Stages 0 and 1 of the plan;
no contrary preference was supplied. The recommended defaults are therefore
accepted. Changing any of them requires a new ADR that supersedes this one.

| # | Decision | Resolution | Rationale | Consequences |
|---|---|---|---|---|
| 1 | Frontend language | Plain `.jsx` with `jsconfig.json` `checkJs` | Matches the plan's starter convention; one language for components and hooks | No compile-time types; strict JSDoc and contract tests compensate |
| 2 | Offline conflict policy | Expense edits/deletes queue for explicit user choice; metadata and star/archive use last-writer-wins | Never silently discard a financial edit | More UI (conflict dialog); conflict rows retained in Dexie |
| 3 | Auth transport | Short-lived JWT access token in memory + rotating `HttpOnly` refresh cookie | Bearer token is not readable by XSS; refresh survives reload | One retry-on-401 path in `api.js`; refresh endpoint needs CSRF protection |
| 4 | Document storage | Local disk by default; S3/R2-compatible adapter optional | Works with zero cloud configuration; preserves fork feature | Storage abstraction and path validation are mandatory |
| 5 | Smart-split scope | Port the existing line-item calculator and category inference only | Preserves the fork's actual behavior; no new conversational feature | No chat assistant; prompts and JSON schemas are frozen |
| 6 | Cutover | Short maintenance window | No bidirectional bridge to build or test | Downtime announcement and rollback rehearsal required |
| 7 | Database | SQLite v1 with WAL; SQLModel kept portable | Matches the fork's shipped databases and single-node deployment | One Uvicorn worker; short transactions; Postgres later without model rewrites |
| 8 | Offline scope | Full group editing offline; admin and AI online-only | Matches M2 goal and the offline-first product promise | Outbox, local calculations and conflict UI are in scope; admin/AI gated |

## Sign-off

- Plan owner: accepted by instruction to execute Stages 0–1 (2026-10-24).
- Engineering: accepted; each decision is elaborated in ADR 0001–0004.
- Open items: none. Any future change must be recorded as a new ADR.
