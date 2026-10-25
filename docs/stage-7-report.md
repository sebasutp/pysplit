# Stage 7 report — receipts and AI smart-split API

Date: 2026-10-25
Stage: 7 (storage, receipt lifecycle, item allocation, apply-to-expense, AI)

## Outcome

The backend now implements the receipt and AI contract from MIGRATION_PLAN.md
§"Stage 7" and `docs/api.md` §10:

- a storage abstraction with local-disk default and an S3-compatible adapter
  (AWS Signature V4 over `httpx`, no vendor SDK);
- receipt image upload with size/type limits, server-generated keys, rate
  limiting and retrieval through the API when storage is local;
- SSRF allowlisting for image URLs sent to the AI provider, with local images
  inlined as `data:` URLs and public S3/R2 URLs passed through;
- an OpenAI-compatible Chat Completions client with `AI_*` precedence over
  `OPENAI_*`, the reference prompts and strict JSON schemas;
- defensive parsing where malformed provider output or provider failure marks
  the receipt `FAILED`, never raises a 500;
- total extraction, item/charge extraction, receipt retrieval by receipt or
  linked expense, item CRUD, portion replacement, opt-outs, apply-to-expense,
  receipt linking and category inference;
- server-side recomputation of provisional totals from stored rows and live
  participants — client totals are never trusted;
- an atomic one-call-per-image claim with stale-claim recovery;
- server-enforced feature flags (`/api/features`), AI/upload rate limits and
  item/portion/name/amount limits;
- pure Python mirrors of the reference receipt split and extraction parsers,
  ready for the Stage 9C JavaScript fixtures.

## Files added

- `backend/app/utils/receipt_split.py` — pure mirror of `receipt-split.ts`
  (portion consumption, clamping, shared/unassigned pools, largest-remainder
  apportionment).
- `backend/app/utils/receipt_extraction.py` — defensive parse and normalization
  of the model response (minor units, quantities, adjustments, item cap).
- `backend/app/storage/base.py` — blob-storage protocol, key validation and the
  local-disk implementation.
- `backend/app/storage/s3.py` — S3-compatible PUT/GET/HEAD/DELETE adapter with
  SigV4 signing and optional public URL.
- `backend/app/services/ai.py` — config precedence, prompt builders, strict JSON
  schemas and the Chat Completions HTTP client.
- `backend/app/services/uploads.py` — receipt image keys/routes, SSRF
  allowlist, local-image resolution to data URLs.
- `backend/app/services/receipts.py` — receipt lifecycle, split computation,
  item/portion/opt-out mutations, apply/link and extraction orchestration.
- `backend/app/schemas/receipts.py` — receipt, item, split, extraction, upload,
  apply, link and category request/response models.
- `backend/app/api/receipts.py` — HTTP-only receipt router plus the `/api/ai`
  category router.
- `backend/tests/test_receipts.py` — split math, lifecycle, claim/stale claim,
  item CRUD, portions, opt-outs, limits, upload, document and S3 tests.
- `backend/tests/test_ai.py` — config precedence, prompts, schema/HTTP contract,
  defensive parsing, extraction endpoints, malformed output, provider failure,
  category inference, title truncation and URL rejection.
- `backend/tests/test_receipt_apply.py` — apply invariants, zero-share filtering,
  persistence of notes/documents, empty/all-opted-out/negative-share guards and
  cross-group rejection.
- `docs/stage-7-report.md` — this report.

## Files changed

- `backend/app/core/config.py` — S3, AI, upload/AI rate limits, receipt limits,
  stale-claim window, `AI_*`/`OPENAI_*` resolution, storage hosts.
- `backend/app/core/enums.py` — `ReceiptStatus` and `ReceiptPortionTarget`.
- `backend/app/core/limits.py` — AI and upload sliding-window limiters.
- `backend/app/services/errors.py`, `backend/app/api/errors.py` — `ForbiddenError`
  mapped to HTTP 403 for server-side flag enforcement.
- `backend/app/storage/local.py`, `backend/app/storage/__init__.py` — re-export
  the shared implementation and add `build_storage(settings)`.
- `backend/app/services/documents.py`, `backend/app/api/expenses.py` — documents
  now use the storage abstraction and stream bytes, so S3 works for both
  documents and receipts.
- `backend/app/main.py` — registers the receipt and AI routers.
- `backend/tests/conftest.py` — resets the AI/upload limiters between tests.
- `backend/tests/helpers.py` — deterministic `make_receipt` fixture builder.
- `backend/tests/test_architecture.py` — receipt router is HTTP-only; receipt
  parsers are pure; Stage 7 specs must exist.
- `backend/tests/test_openapi.py` — requires the Stage 7 paths and excludes the
  raw image response from the schema rule.
- `.env.example`, `backend/.env.example` — S3, AI, upload and receipt limits.
- `docs/api.md` — accurate Stage 7 request/response shapes and flag gates.
- `docs/openapi.json` — regenerated snapshot (54 paths).
- `docs/parity-matrix.yml`, `docs/parity-report.md` — Stage 7 receipt, upload,
  extraction, claim, limit and category rows.

No database migration was required: `receipts`, `receipt_items`,
`receipt_item_portions`, `receipt_opt_outs`, the versioning columns and the
storage-independent document tables already exist from migrations `0002` and
`0003`. `alembic check` reports no new upgrade operations.

## Design details

### Storage

`BlobStorage` has five operations: `save`, `read`, `delete`, `exists` and
`public_url`. Keys are validated as relative POSIX paths with no `..`, so a
caller can never turn a key into path traversal. `build_storage(settings)`
selects S3 when the credential/bucket/region quartet is present; otherwise
local disk is used. The S3 adapter signs requests with SigV4 and addresses
objects path-style, which works with AWS, R2 and MinIO. It creates the HTTP
client lazily, so merely constructing the adapter (for a public URL) does not
need TLS trust stores.

### Receipt split math

Each item's money is apportioned over the quantities its portions claim using
the existing largest-remainder `weighted_apportion`. Portion quantities are
floored, non-positive quantities are dropped, unknown participant portions are
ignored, and every portion is clamped to the item's remaining quantity. The
remainder becomes the unassigned pool shared by participants who did not opt
out. Shared portions (charges) are spread over everyone, opt-outs included.
`all_opted_out` blocks Apply when the unassigned pool has nobody to land on.

### Extraction and claim

`create_pending_receipt` relies on the `(group_id, image_url)` unique
constraint and returns the winning row on a race. `claim_receipt_for_extraction`
performs one conditional `UPDATE` that wins only for `PENDING`/`FAILED` rows or
an `EXTRACTING` row older than `RECEIPT_EXTRACTION_STALE_SECONDS`; the rowcount
decides the single winner. `complete_receipt` replaces all existing items in
the same transaction, and `fail_receipt` records the raw/provider/model
metadata so retries remain possible.

### AI and SSRF

The provider receives the same prompt text and JSON schemas as the reference.
Configuration resolution is centralized: `AI_API_KEY`/`AI_BASE_URL`/`AI_MODEL_*`
override the historical `OPENAI_*` names, and the items model falls back to the
receipt-extract model. URLs are accepted only when they are the API's own
upload routes or an absolute http(s) URL on a configured storage/application
host. Local images are read from blob storage and sent as inline data URLs;
public storage URLs are passed through. This blocks arbitrary attacker URLs,
`data:`/`javascript:` schemes, unrelated hosts and subdomain lookalikes without
adding an outbound fetch server-side.

### Apply

Apply always recomputes the split from stored rows, refuses empty receipts,
all-opted-out receipts and negative participant totals, filters zero shares so
`BY_AMOUNT` stays valid, and updates the expense plus the receipt link in one
transaction. Notes, documents, payer, recurrence and the expense date are
preserved because only `amount`, `split_mode` and `paid_for` are patched.

## Verification commands and output

### Stage 7 suite (plan command)

```bash
$ cd backend
$ PYTHONPATH=. .venv-work/bin/pytest tests/test_receipts.py tests/test_ai.py \
    tests/test_receipt_apply.py -n auto
...
======================= 50 passed, 25 warnings in 6.34s ========================
```

The repository virtualenv is the known sandbox artefact documented in earlier
reports; `.venv-work/bin/pytest` is the working interpreter behind
`backend/.venv`.

### Full backend suite with coverage

```bash
$ PYTHONPATH=. .venv-work/bin/pytest -n auto
...
Required test coverage of 80% reached. Total coverage: 91.87%
======================= 262 passed, 25 warnings in 9.85s =======================
```

### Lint and formatting

```bash
$ .venv-work/bin/ruff check .
All checks passed!

$ .venv-work/bin/ruff format --check .
132 files already formatted
```

### Alembic

```bash
$ DATABASE_URL=sqlite:////tmp/stage7-alembic.db .venv-work/bin/alembic upgrade head
$ DATABASE_URL=sqlite:////tmp/stage7-alembic.db .venv-work/bin/alembic check
No new upgrade operations detected.
```

### OpenAPI and parity matrix

```bash
$ backend/.venv-work/bin/python backend/scripts/export_openapi.py
Wrote docs/openapi.json (54 paths)

$ backend/.venv-work/bin/python scripts/check_parity_matrix.py
OK: 123 features; 14 pages, 28 procedure files, 30 Jest suites, 14 Playwright specs all mapped.
```

### No real AI calls

Every AI test injects a deterministic `FakeAiClient` or an `httpx.MockTransport`.
The suite performs zero network calls to a model provider. The sample receipt
case (items + charge + synthesized adjustment) produces the reference totals:
items 2000 + 1000 + charge 200 with a −200 adjustment, `items_total = 3000`.

## Gate checklist

| Gate item | Status |
|---|---|
| Storage abstraction with local default and S3-compatible adapter | Pass |
| Upload size/type limits, server-generated keys, traversal protection | Pass |
| SSRF allowlist for URLs sent to the AI provider | Pass |
| `AI_*` precedence over `OPENAI_*` and model fallbacks | Pass |
| Reference prompts and strict JSON schemas ported | Pass |
| Malformed output/provider failure becomes `FAILED`, never a crash | Pass |
| Total extraction endpoint | Pass |
| Item/charge extraction endpoint | Pass |
| Receipt retrieval by receipt id and linked expense | Pass |
| Item create/update/delete | Pass |
| Portion replacement and opt-outs | Pass |
| Apply-to-expense and receipt link | Pass |
| Category inference endpoint | Pass |
| Server recomputation of provisional totals | Pass |
| Atomic one-call-per-image claim and stale-claim recovery | Pass |
| Server-enforced feature flags on all receipt/AI endpoints | Pass |
| Item/portion/name/amount limits | Pass |
| AI and upload rate limits | Pass |
| Mocked tests for flags, malformed output, unassigned/shared items, adjustments, claims, fractional splits, opt-outs and apply invariants | Pass |
| Sample receipt provisional totals match reference behavior | Pass |
| Full suite, coverage, lint, format, Alembic, OpenAPI and parity checker green | Pass |

**Gate: PASSED.**

## Deviations and open questions

1. **Total extraction returns the reference-shaped fields, not a persisted
   `Receipt`.** `POST .../receipts/extract-total` returns
   `{amount, category_id, date, title}`. Persisting an `EXTRACTED` receipt there
   would make a later item extraction reuse an empty parse and skip the paid
   call; the reference action itself does not persist either. Item extraction
   persists the receipt. `docs/api.md` describes the implemented behavior.
2. **Relative app URLs are accepted by the SSRF guard for local storage.** The
   reference only accepts absolute S3 URLs. Because local disk is the default
   backend, receipt images have relative app URLs until S3 is configured. Those
   URLs are resolved by reading the app's own blob store and are sent inline;
   external absolute URLs still have to be on the configured allowlist.
3. **S3 uses `httpx` + SigV4 instead of a vendor SDK.** This keeps the
   dependency set unchanged (`httpx` already exists) and supports AWS, R2 and
   MinIO path-style endpoints. A dedicated SDK was not added because plan §2.1
   does not list one.
4. **Category inference returns only `{category_id}`.** The reference action
   returns only the id; the earlier `docs/api.md` example also showed a
   `confidence` field, which is not produced by the reference behavior and was
   removed from the documentation.
5. **Receipt endpoints require `receipt_items`; total extraction requires
   `receipt_extract`.** This mirrors the reference `receiptProcedure` gate. The
   upload endpoint is allowed when either extraction flag is on.
6. **S3 is optional, not required when documents are enabled.** Local disk
   remains a supported default. The reference required `S3_*` when document
   uploads were enabled; the migration plan explicitly says "local disk by
   default plus an S3 adapter."
7. **The in-process rate limiter is single-worker only.** This is consistent
   with the Stage 6/auth limiter and the Stage 12 SQLite deployment model. A
   shared store is needed if the API grows past one process.
8. **`receipt.total` is `normalized.total ?? itemsTotal`; `items_total` in the
   split always sums the stored item rows, including a synthesized adjustment.**
   This is why the sample extraction reports 3000 after adding a −200
   adjustment over 2000 + 1000 + 200.
9. **Receipt push/pull entity appliers are not part of Stage 7.** Stage 6
   reserved them for "Stage 7's receipt API work"; they are instead deferred to
   Stage 9B, which owns the outbox entity wiring and conflict UI. The Stage 7
   gate covers the receipt/AI REST contract, and bootstrap already carries
   receipt snapshots. This is the only Stage 6 note that needs correction.

## Intentionally deferred

- Receipt/portion/opt-out push and pull appliers, and the client outbox
  (Stage 9B).
- Receipt items UI, fractional assignment UI, provisional-total footer,
  divergence note and admin receipt screens (Stage 8D).
- Offline AI controls, queued receipt uploads and "scan pending" state
  (Stage 10B).
- Scheduled rate-limit storage, structured logs, S3 lifecycle/retention policies
  and production deployment tuning (Stage 12).
