# HTTP API contract

Status: frozen for M1/M2
Related: `docs/repository-contract.md`, `docs/adr/0003-auth.md`

Base path: `/api`. JSON only, `snake_case`. Money is integer minor units;
conversion rates and quantities are decimal/integer strings as stated below.

## 1. Conventions

| Topic | Rule |
|---|---|
| List envelope | `{ "items": [], "total": 0, "limit": 50, "offset": 0 }` |
| Cursor envelope | `{ "items": [], "next_cursor": null, "has_more": false }` |
| Error | `{ "detail": "human readable" }` |
| Validation error | FastAPI 422 `{ "detail": [{ "loc": [], "msg": "", "type": "" }] }` |
| Create | `201` + full entity |
| Delete | `204`, empty body |
| Partial update | `PATCH` + full updated entity |
| Timestamps | ISO 8601 UTC with `Z` |
| `expense_date` | `YYYY-MM-DD` at the boundary |
| IDs | strings; never infer UUID format |
| Auth | `Authorization: Bearer <access>` for account mutations; group endpoints are public capability URLs |
| Idempotency | create accepts client `id`; sync operations use `op_id` |
| CORS | explicit origin allowlist; credentials allowed only there |

Health endpoints are unauthenticated. Admin endpoints require `admin`.
Group creation requires `group_creators` or `admin`.
The reviewed runtime contract is snapshotted in `docs/openapi.json`; regenerate
it with `backend/.venv/bin/python backend/scripts/export_openapi.py`.

## 2. Health and features

### `GET /api/health`
```json
{ "status": "ok", "version": "0.1.0" }
```

### `GET /api/health/liveness`
```json
{ "status": "alive" }
```

### `GET /api/health/readiness`
Runs `SELECT 1`. `200` when ready, `503` when the database is unavailable.
```json
{ "status": "ready", "checks": { "database": "ok" } }
```

### `GET /api/features`
Returns server-enforced flags so the SPA never enables a disabled feature.
```json
{
  "receipt_extract": false,
  "receipt_items": false,
  "category_extract": false,
  "expense_documents": false
}
```

## 3. Authentication

### `GET /api/auth/me`
`200` with the user, or `200 { "user": null }` when anonymous. `providers`
mirrors the reference discovery endpoint and reports which OAuth providers have
both credentials configured.
```json
{
  "user": {
    "id": "usr_...",
    "name": "Ada",
    "email": "ada@example.com",
    "image": null,
    "tier": "sync_users"
  },
  "providers": { "google": true, "github": false }
}
```

### `GET /api/auth/oauth/{provider}/start?return_to=/groups`
`provider` is `google` or `github`. Sets an `HttpOnly` state cookie and
redirects to the provider. `return_to` must be a relative same-origin path.

### `GET /api/auth/oauth/{provider}/callback?code=…&state=…`
Validates state, exchanges the code, links/creates the user, sets the refresh
cookie, and redirects to `return_to` (default `/groups`). Account linking
requires a provider email that is verified by the provider: an unverified email
is rejected with `403` and is never auto-linked. Other errors redirect with
`?error=InvalidOAuthState|OAuthExchangeFailed|OAuthNotConfigured`.

### `POST /api/auth/refresh`
Requires the refresh cookie, the readable `pysplit_csrf` cookie echoed in
`X-CSRF-Token`, and a same-origin `Origin` (or `Referer`). Rotates the refresh
token and returns a new access token.
```json
{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 900,
  "user": { "id": "usr_...", "tier": "sync_users" } }
```
Reuse of an already-rotated token returns `401` and revokes the family.

### `POST /api/auth/logout`
Requires the same CSRF and origin checks. Revokes the whole refresh-token
rotation family, clears the session cookies, returns `204`.

### `POST /api/auth/mock-login` (development/test only)
Disabled by default. Requires `ENABLE_MOCK_LOGIN=true` and is always unavailable
(`404`) when the flag is off or `ENVIRONMENT=production`. It bypasses normal
OAuth sign-in, so never enable it on a public deployment. Used by the Playwright
helpers.
```json
{ "email": "test@example.com", "name": "Test", "tier": "group_creators" }
```

## 4. Groups and participants

### `GET /api/groups?ids=id1,id2`
Returns groups for the given IDs (the reference fetches recent IDs from local
storage). Without `ids`, returns the authenticated user's groups. Query
parameters: `status=recent|starred|archived|all` (auth only).
```json
{ "items": [ { "id": "g1", "name": "Trip", "currency": "$",
  "currency_code": "USD", "information": null,
  "created_at": "2026-10-24T12:00:00Z", "updated_at": "2026-10-24T12:00:00Z",
  "version": 1, "deleted_at": null,
  "participants": [ { "id": "p1", "name": "Ada", "group_id": "g1" } ] } ],
  "total": 1, "limit": 50, "offset": 0 }
```

### `POST /api/groups`
```json
{
  "id": "optional-client-id",
  "name": "Trip",
  "information": "Lisbon",
  "currency": "$",
  "currency_code": "USD",
  "participants": [ { "id": "p1", "name": "Ada" } ]
}
```
`201` with the group. Requires tier `group_creators`/`admin`.

### `GET /api/groups/{group_id}`
Full group with participants, or `404`.

### `GET /api/groups/{group_id}/details`
`participants_with_expenses` is the reference-compatible list of participant IDs
that appear as payer or paid-for on an expense. The same participants are also
returned as objects in `participants_with_expense_details`.
```json
{ "group": { "...": "..." },
  "participants_with_expenses": ["p1"],
  "participants_with_expense_details": [ { "id": "p1", "name": "Ada" } ] }
```

### `PATCH /api/groups/{group_id}`
Accepts `name`, `information`, `currency`, `currency_code`, `participants`
(replace-set), optional `participant_id` (the active participant). Returns the
updated group. Participant rename/removal is handled here to match the
reference form.

### `POST /api/groups/{group_id}/access`
Records that the authenticated user visited the group (upsert `UserGroup`).
`204`.

### `PATCH /api/groups/{group_id}/membership`
```json
{ "is_starred": true, "is_archived": false }
```
Last-writer-wins per user. Returns the membership.

### `DELETE /api/groups/{group_id}/membership`
Removes the group from the user's synchronized list without deleting data.
`204`.

### `POST /api/groups/sync`
Merges locally known group IDs into the authenticated user's `UserGroup` rows.
```json
{ "group_ids": ["g1", "g2"] }
```
```json
{ "is_authenticated": true,
  "user_groups": [ { "group_id": "g1", "is_starred": false, "is_archived": false } ],
  "groups": [ { "id": "g1", "name": "Trip" } ] }
```
Idempotent: existing rows are not duplicated.

## 5. Categories

### `GET /api/categories`
```json
{ "items": [ { "id": 1, "grouping": "Entertainment", "name": "Games" } ],
  "total": 44, "limit": 200, "offset": 0 }
```
Seeded on first run; never empty.

## 6. Expenses

### `GET /api/groups/{group_id}/expenses?limit=50&offset=0&from=2026-01-01&to=2026-12-31`
Ordered by `expense_date DESC, created_at DESC, id ASC`.
```json
{
  "items": [{
    "id": "e1", "group_id": "g1", "expense_date": "2026-09-03",
    "title": "Dinner", "category_id": 1, "amount": 159600,
    "original_amount": null, "original_currency": null, "conversion_rate": null,
    "paid_by_id": "p1", "is_reimbursement": false, "split_mode": "EVENLY",
    "notes": null, "recurrence_rule": "NONE",
    "created_at": "2026-09-03T11:23:49Z", "updated_at": "2026-09-03T11:23:49Z",
    "version": 1, "deleted_at": null,
    "paid_for": [ { "participant_id": "p1", "shares": 1 } ],
    "documents": [],
    "receipt": null
  }],
  "total": 1, "limit": 50, "offset": 0
}
```

### `POST /api/groups/{group_id}/expenses`
```json
{
  "id": "optional-client-id",
  "expense_date": "2026-09-03",
  "title": "Dinner",
  "category_id": 1,
  "amount": 159600,
  "original_amount": 150000,
  "original_currency": "EUR",
  "conversion_rate": "1.0640",
  "paid_by_id": "p1",
  "is_reimbursement": false,
  "split_mode": "BY_AMOUNT",
  "notes": "Team dinner",
  "recurrence_rule": "MONTHLY",
  "paid_for": [ { "participant_id": "p1", "shares": 1, "amount": 79800 } ]
}
```
For `BY_SHARES`, `shares` is an integer; for `BY_PERCENTAGE`, `shares` is an
integer percentage or the API accepts `percentage`; for `BY_AMOUNT`, each
participant's `amount` must sum exactly to `amount`. Validation returns `422`
with field locations.

Input bounds (create and update): `title` ≤ 200 characters, `paid_for` ≤ 100
rows (create requires at least one), `documents` ≤ 20, `shares` ≤ 1,000,000, and
`conversion_rate` at most 18 digits with at most 9 decimal places. Exceeding any
bound returns `422`.

### `GET /api/groups/{group_id}/expenses/{expense_id}`
Full expense or `404`.

### `PATCH /api/groups/{group_id}/expenses/{expense_id}`
Partial update; changing split mode replaces `paid_for`. An optional
`base_version` (also accepted as camelCase `baseVersion`) enables optimistic
concurrency: when supplied it must equal the stored `version`, and a mismatch
returns `409` without applying the update. When omitted, the update is
last-writer-wins. Recurring expenses cannot change their rule after
materialization; the server returns `409`. Returns the updated expense.

### `DELETE /api/groups/{group_id}/expenses/{expense_id}`
`204`. Writes an activity row and a tombstone.

### Recurrence
The server materializes due frames on list/get/stats reads, exactly like the
reference. `next_expense_created_at` prevents duplicates. Clients never create
recurrence frames themselves; offline clients display already-materialized
frames and receive future frames after synchronization.

### Documents
- `POST /api/groups/{group_id}/expenses/{expense_id}/documents` — multipart
  upload (`file`, optional `width`/`height`). Limits: 10 MB,
  `image/jpeg|png|webp`, local disk (S3 in Stage 7).
- `GET /api/groups/{group_id}/expenses/{expense_id}/documents/{document_id}` —
  returns the blob inline with `Content-Disposition`.
- `DELETE /api/groups/{group_id}/expenses/{expense_id}/documents/{document_id}` —
  `204`.

Uploads reject path traversal, executable content types and oversized files.
Storage keys are server-generated. When `ENABLE_EXPENSE_DOCUMENTS=false` (the
default), upload, download and delete all return `403`.

## 7. Balances

### `GET /api/groups/{group_id}/balances`
```json
{
  "balances": [
    { "participant_id": "p1", "total": 1200 },
    { "participant_id": "p2", "total": -1200 }
  ],
  "reimbursements": [ { "from": "p2", "to": "p1", "amount": 1200 } ]
}
```
Positive means the participant is owed.

### `GET /api/balances?groups=g1:p1,g2:p3`
Global balance for an active participant per group.
```json
{ "items": [ { "group_id": "g1", "group_name": "Trip", "currency": "$",
  "currency_code": "USD", "participant_id": "p1", "participant_name": "Ada",
  "amount": 1200 } ] }
```

## 8. Statistics

### `GET /api/groups/{group_id}/stats?participant_id=p1&from=2026-01-01&to=2026-12-31`
```json
{
  "range": { "from": "2026-01-01", "to": "2026-12-31" },
  "total_group_spending": 159600,
  "total_active_user_share": 79800,
  "total_active_user_paid_for": 79800,
  "spending_over_time": [ { "period": "2026-09", "amount": 159600 } ],
  "spending_by_participant": [ { "participant_id": "p1", "amount": 159600 } ],
  "spending_by_category": [ { "category_id": 1, "amount": 159600 } ],
  "recurring": { "active_count": 0, "monthly_amount": 0 }
}
```

### `GET /api/groups/{group_id}/stats/categories/{category_id}/expenses?from=&to=`
### `GET /api/groups/{group_id}/stats/months/{month}/expenses?from=&to=`
Both return `{ "expenses": [ { "id", "title", "amount", "expense_date" } ] }`.
`month` is `YYYY-MM`.

## 9. Activities

### `GET /api/groups/{group_id}/activities?cursor=0&limit=5`
```json
{
  "items": [ { "id": "a1", "time": "2026-09-03T11:23:49Z",
    "activity_type": "EXPENSE_CREATED", "participant_id": "p1",
    "expense_id": "e1", "data": "..." } ],
  "next_cursor": "5", "has_more": false
}
```
`Activity` has no foreign key to `Expense`; orphan activities are returned.

## 10. Receipts and AI

Receipt GET/item/apply/link endpoints require `receipt_items` to be enabled.
`extract-total` requires `receipt_extract` (which is implied by
`receipt_items`). AI extraction is online-only.

**Authentication.** The three AI endpoints (`extract-total`, `extract-items`
and `/api/ai/categories/infer`) require an authenticated user: send
`Authorization: Bearer <access>` or receive `401`. They are rate limited per
caller (`429`). All limits and flags are enforced server-side, not only by the
UI.

### `POST /api/groups/{group_id}/receipts/upload`
Multipart upload (`file`, optional `width`, `height`). Accepts the configured
image types, enforces `MAX_UPLOAD_BYTES`, and returns a server-generated URL:
```json
{ "url": "/api/groups/g1/receipts/images/img_…", "width": 800, "height": 600 }
```
When S3/R2 public storage is configured the URL points directly at storage.
Uploads are rate-limited and keys are server-generated and group-scoped
(`receipts/{group_id}/…`), so traversal is not possible. An image id referenced
through a different group's route is rejected.

### `GET /api/groups/{group_id}/receipts/images/{image_id}`
Returns the stored image bytes. Used for local-disk storage only. Only images
stored under that group's prefix (or legacy images with a receipt row proving
ownership) are served.

### `GET /api/groups/{group_id}/receipts/{receipt_id}`
### `GET /api/groups/{group_id}/expenses/{expense_id}/receipt`
```json
{
  "receipt": { "id": "r1", "group_id": "g1", "image_url": "...",
    "status": "EXTRACTED", "attempts": 1, "provider": "openai-compatible",
    "merchant": "Cafe", "receipt_date": "2026-09-03",
    "currency_code": "EUR", "total": 2400 },
  "items": [ { "id": "i1", "name": "Pasta", "quantity_milli": 1000,
    "unit_price": 1200, "amount": 1200, "is_shared": false,
    "is_adjustment": false, "position": 0,
    "portions": [ { "id": "rp1", "target": "PARTICIPANT",
      "participant_id": "p1", "quantity_milli": 1000 } ] } ],
  "opt_outs": [ "p2" ],
  "split": { "participant_totals": [ { "participant_id": "p1", "amount": 1200 } ],
    "participants": [ { "participant_id": "p1", "direct": 1200, "shared": 0,
      "unassigned": 0, "total": 1200 } ],
    "unassigned": 0, "unassigned_pool": 0, "shared": 0, "shared_pool": 0,
    "adjustments": 0, "items_total": 1200, "total": 1200,
    "all_opted_out": false }
}
```
Provisional totals are always recomputed from stored items and live
participants. Client-supplied totals are never trusted. `ReceiptRead.attempts`
counts paid extraction claims. `ReceiptRead.provider` is a stable public label —
`openai-compatible`, `google` or `disabled` — never the internal AI base URL.

### `POST /api/groups/{group_id}/receipts/extract-total`
```json
{ "image_url": "/api/groups/g1/receipts/images/img_…" }
```
```json
{ "amount": 42.5, "category_id": "7", "date": "2026-04-01", "title": "Lunch" }
```
The reference-shaped result is returned without persisting a receipt, so the
follow-up line-item extraction still performs the single paid call. Malformed
model output or a provider failure returns all-null fields, never a 500.

### `POST /api/groups/{group_id}/receipts/extract-items`
Same input plus optional `image_width`/`image_height`. The first successful
call per `(group_id, image_url)` persists an `EXTRACTED` receipt; re-posting the
same image reuses it without another paid call. Returns:
```json
{ "status": "EXTRACTED", "receipt_id": "r1", "total": 2400,
  "items_total": 2400, "merchant": "Cafe", "date": "2026-04-01",
  "currency_code": "EUR", "category_id": "7",
  "receipt": { "…": "ReceiptRead" }, "items": [], "opt_outs": [],
  "split": { "…": "ReceiptSplitRead" } }
```
Malformed output or a provider failure records `status: "FAILED"` on the
receipt and returns `status: "FAILED"` with an empty split. Concurrent callers
race on an atomic claim; a stale `EXTRACTING` claim is recoverable after
`RECEIPT_EXTRACTION_STALE_SECONDS`. The loser receives `409`.

Each paid extraction claim increments `attempts`. Retries are bounded by
`RECEIPT_MAX_ATTEMPTS` (default 3); once the cap is reached, further extraction
of that image returns `409` and the image must be uploaded again. Re-posting an
already `EXTRACTED` image reuses the stored receipt without another paid call.

### `POST /api/groups/{group_id}/receipts/{receipt_id}/items`
### `PATCH /api/groups/{group_id}/receipts/{receipt_id}/items/{item_id}`
### `DELETE /api/groups/{group_id}/receipts/{receipt_id}/items/{item_id}`
Create fields: `name`, `quantity_milli`, `amount`, `is_shared`.
Update fields: any of `name`, `quantity_milli`, `amount`, `is_shared`.
Limits: name ≤ 200 characters, amount ≤ 1,000,000,000 minor units,
quantity ≤ 1,000,000,000 thousandths. Every mutation returns `ReceiptState`.

### `PUT /api/groups/{group_id}/receipts/{receipt_id}/items/{item_id}/portions`
Replace-set:
```json
{ "portions": [ { "target": "PARTICIPANT", "participant_id": "p1", "quantity_milli": 500 },
                { "target": "SHARED", "quantity_milli": 500 } ] }
```
At most 100 portions. Participant portions must name a live group participant,
and the summed quantities may not exceed the item quantity. An empty list
returns the item to the unassigned pool and clears `is_shared`.

### `PUT /api/groups/{group_id}/receipts/{receipt_id}/opt-outs/{participant_id}`
`{ "opted_out": true }`; returns `ReceiptState`.

### `POST /api/groups/{group_id}/receipts/{receipt_id}/apply`
```json
{ "expense_id": "e1", "participant_id": "p1" }
```
Updates the expense to a `BY_AMOUNT` split using the server-recomputed split,
preserves its notes/documents/paid-by/recurrence, and links the receipt.
All-opted-out, empty and negative-share receipts are rejected with `422`.
Returns `{ "receipt", "expense", "split" }`.

### `POST /api/groups/{group_id}/receipts/{receipt_id}/link`
`{ "expense_id": "e1" }`; `404` if either side belongs to another group.

### `POST /api/ai/categories/infer`
```json
{ "title": "Team dinner" }
```
```json
{ "category_id": 1 }
```
The title is truncated to 40 characters before the model call. Unknown or
malformed model output falls back to category `0` (General). Requires bearer
authentication (`401` without it), respects `ENABLE_CATEGORY_EXTRACT`, and is
rate-limited (`429`).


## 11. Exports

### `GET /api/groups/{group_id}/expenses/export.csv?from=&to=`
`text/csv` with the reference columns and labels. Formula-injection prefixes
(`=`, `+`, `-`, `@`) are escaped.

### `GET /api/groups/{group_id}/expenses/export.json?from=&to=`
`application/json` with the same normalized expense rows.

## 12. Admin

All admin endpoints require tier `admin`; unauthenticated → 401, wrong tier →
403.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/metrics` | user/group/expense counts and tier breakdown |
| GET | `/api/admin/users?q=&tier=&limit=&offset=` | search users |
| POST | `/api/admin/users/preauthorize` | pre-authorize an email/tier |
| PATCH | `/api/admin/users/{user_id}/tier` | change tier |
| DELETE | `/api/admin/users/{user_id}` | delete user (`204`) |
| GET | `/api/admin/groups?q=&limit=&offset=` | search groups |
| DELETE | `/api/admin/groups/{group_id}` | delete group and children (`204`) |

List endpoints use `{ "items": [...], "total": N, "limit": N, "offset": N }`.
User items carry `id`, `name`, `email`, `image`, `tier`, `created_at`,
`providers` and `groups_count`; group items carry `id`, `name`, `currency`,
`currency_code`, `created_at`, `participants_count`, `expenses_count` and
`synced_users_count`. `POST /preauthorize` returns `{ "user": ..., "is_new":
bool }`. Authentication failures are `401`; authenticated non-admin callers
receive `403`.

## 13. Synchronization

See ADR 0002 for the full protocol. All `/api/sync/*` endpoints are rate limited
per caller (`SYNC_RATE_LIMIT_PER_MINUTE`, default 120 per minute); exceeding the
budget returns `429` with `Retry-After`.

### `GET /api/sync/bootstrap?group_id=…`
```json
{ "cursor": 123, "group": { "...": "..." }, "participants": [],
  "expenses": [], "activities": [], "receipts": [], "categories": [] }
```

### `POST /api/sync/pull`
```json
{ "cursor": 100, "group_ids": ["g1"], "limit": 500 }
```
```json
{ "changes": [ { "seq": 101, "entity_type": "expense", "entity_id": "e1",
  "op_type": "update", "snapshot": { "...": "..." } } ],
  "cursor": 123, "has_more": false }
```

### `POST /api/sync/push`
```json
{ "operations": [ { "op_id": "uuid", "group_id": "g1",
  "entity_type": "expense", "entity_id": "e1", "op_type": "update",
  "base_version": 3, "payload": { "title": "Dinner" },
  "client_time": "2026-10-24T12:00:00Z" } ] }
```
Returns one result per operation plus a cursor; see ADR 0002.

Supported `entity_type` values and their allowed payload fields are defined by
the server whitelist (`backend/app/services/sync.py::ENTITY_FIELDS`):

| Entity | Operations | Payload |
|---|---|---|
| `group` | create, update | `name`, `information`, `currency`, `currency_code`; create also accepts `participants` |
| `participant` | create, update, delete | `name` for create/update |
| `expense` | create, update, delete | the `ExpenseCreate`/`ExpenseUpdate` fields (`expense_date`, `title`, `amount`, `paid_for`, ...) |
| `user_group` | create, update, delete | `is_starred`, `is_archived`; requires authentication |

Unknown entity types and unknown top-level or nested fields are rejected per
operation with `status: "error"`; other operations in the batch are still
applied. Group metadata, participant names and star/archive membership are
last-writer-wins. Expense updates and deletes require a matching
`base_version`; stale writes return `status: "conflict"` with `server_entity`.
Deletes are tombstones and win over later updates.

A pull cursor older than the 30-day retained change log (or newer than the
server feed) returns `409` with `{ "detail": "bootstrap_required" }`; call
`GET /api/sync/bootstrap` and restart from its cursor.

## 14. Status codes

| Code | Use |
|---|---|
| 200 | read/update success |
| 201 | create |
| 204 | delete/logout/access |
| 400 | malformed request |
| 401 | missing/invalid access token (including the AI endpoints) |
| 403 | tier, CSRF, unverified OAuth email, or a disabled feature flag |
| 404 | unknown entity (including cross-group access, to avoid leaks) |
| 409 | stale version, exhausted AI retries, duplicate link, immutable recurrence |
| 422 | schema validation |
| 429 | rate limited (auth, AI, uploads or `/api/sync/*`) |
| 503 | readiness failure |
