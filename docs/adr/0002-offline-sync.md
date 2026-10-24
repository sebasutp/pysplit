# ADR 0002 — Offline synchronization

Status: Accepted
Date: 2026-10-24
Related: ADR 0000 decisions 2 and 8

## Context

The application is offline-first: after a group has been synchronized, users
must read and edit it without a network. Pending edits must survive reloads and
must never be silently lost. The reference app is online-only; cross-device
group sync exists, but there is no offline write queue.

## Decision

### Entity versioning

Every synchronizable row carries:

| Column | Semantics |
|---|---|
| `id` | string, client-generated, legacy IDs preserved |
| `updated_at` | UTC, server-set on every write |
| `version` | integer, incremented on every server write |
| `deleted_at` | nullable tombstone |
| `group_id` | owning group where applicable |

### Operation envelope

```json
{
  "op_id": "uuid",
  "group_id": "group-id",
  "entity_type": "expense",
  "entity_id": "expense-id",
  "op_type": "create | update | delete",
  "base_version": 3,
  "payload": { "validated entity fields only": "..." },
  "client_time": "2026-10-24T12:00:00Z"
}
```

`entity_type` and payload fields are checked against explicit server-side
whitelists. Unknown entity types, unknown fields and cross-group operations are
rejected with `error`.

### Push

`POST /api/sync/push` accepts at most 50 operations. Each operation runs in its
own transaction, appends one `sync_changes` row, and receives an independent
result:

```json
{
  "results": [
    {"op_id": "…", "status": "applied", "entity": {}, "version": 4, "seq": 123},
    {"op_id": "…", "status": "conflict", "server_entity": {}, "version": 5},
    {"op_id": "…", "status": "error", "code": "validation_error", "detail": "…"}
  ],
  "cursor": 123
}
```

A request is not rolled back as a whole because one operation fails: financial
edits that are valid must not be blocked by an unrelated invalid one. Each
operation's effects and change-log row are atomic.

### Pull and bootstrap

`POST /api/sync/pull` takes `{cursor, group_ids, limit}` and returns full
snapshots (not diffs): `{changes, cursor, has_more}`. `GET
/api/sync/bootstrap?group_id=…` returns a full group snapshot plus the current
cursor. Bootstrap is used for first synchronization and whenever the cursor is
older than the 30-day change-log retention.

### Conflict rules

| Entity | Rule |
|---|---|
| Group metadata, participant names | Last writer wins |
| Star/archive membership | Last writer wins per user |
| Expense create | Idempotent by entity and operation ID; duplicate returns existing row |
| Expense update/delete | Conflict queue; UI offers keep mine / use server / duplicate as new |
| Receipt item/portion edits | LWW per item; portions are a versioned replace-set |
| Delete versus update | Tombstone wins; UI shows "deleted elsewhere" |

### Idempotency and ordering

- `sync_operations(op_id PRIMARY KEY, user_id, applied_at, result_json)`
  retains results for 7 days. A replayed operation returns the stored result.
- Clients send operations FIFO per group.
- `base_version` is required for update/delete; stale versions conflict.
- `sync_changes.seq` is an autoincrementing sequence; pull pages by `seq`.
- Change-log rows are compacted after 30 days; a cursor older than the oldest
  retained row forces bootstrap.

### Client coordination

- One outbox row per local mutation, written in the same Dexie transaction as
  the local row.
- Push then pull; pull applies in one Dexie transaction.
- Single-flight via `navigator.locks`; `BroadcastChannel` elects one leader
  across tabs. Other tabs receive applied changes and refresh.
- Retry with exponential backoff; startup, `online`, `visibilitychange`,
  debounced mutation, 60-second interval online, and manual retry all trigger
  synchronization.

## Consequences

- The server is authoritative for validation, canonical IDs, timestamps,
  activity, recurrence and AI.
- Client-generated IDs let offline creates appear immediately and remain
  stable after push.
- Conflict UI is required in Stage 9B; it cannot be deferred without violating
  decision 2.
- The change log and operation table are part of the Stage 2 schema, not an
  afterthought.

## Rejected alternatives

- **CRDTs.** Rejected: complex, unnecessary for expense records, and the plan
  excludes them.
- **Automatic LWW for expenses.** Rejected: can erase a financial edit.
- **Diff-based pull.** Rejected: replaying partial diffs is fragile after a
  missed cursor; snapshots are simpler and self-healing.
- **Whole-request transaction.** Rejected: one bad operation would block valid
  offline work.
