# Human review — Round 1 plan

Status: implemented in this change set.

Revision 2: the app has never been used in production, so this plan now chooses
the **destructive simplification** instead of keeping backward compatibility.
There is no production data to migrate, and no need to preserve the old
documents-vs-receipts API, tables, feature flags or offline schema. Developer
databases may be recreated from scratch.

This plan addresses every item in `docs/human-review.md`. It replaces the two
separate file concepts with one destructive attachment model, and adds
local-only AI mocking so receipt parsing can be tested with no API key or
provider call.

## Review item → plan

| Review item | Plan |
| --- | --- |
| README: how to configure Gemini/DeepSeek for receipt AI; dev vs prod; mock flag | §1 |
| Receipt is not visible in the UI after upload; want thumbnail and full-screen view | §2.2 |
| Documents only accept images, are uncompressed, and can only be opened in a new window | §2.2, §2.3 |
| Documents and receipts should not be separate concepts; allow PDF attachments | §2.1–§2.3 |
| Create expense from receipt, or create the expense first and process its receipt with AI | §2.4 |
| Activity says “created by Someone” although the user is logged in | §3 |
| Hide the Information tab when information is empty | §4 |
| Remove all references of this being made in Quebec (was actually made in Zurich) | 4.1 |

## Decisions and answers

**“Why are receipts and documents separate today?”** Internally they are two
different things:

- a receipt is an AI-processing record with a status, attempts, extracted
  merchant/total/currency, line items, portions, opt-outs and a split;
- an expense document is a generic file attachment.

The extraction state is useful; the separate file concept is not. Because there
is no production data, the plan **collapses them into one `Attachment` table**
and one API surface. A receipt becomes an attachment with receipt-processing
fields; a generic document is the same row with no receipt status. This deletes
`expense_documents`, renames/replaces `receipts`, removes the duplicated upload/
download code paths, and removes the “merge two lists in the UI” workaround. It
also lets the offline outbox and Dexie schema drop their duplicated
`document_upload`/`receipt_upload` entities.

**Multi-item receipts and per-person assignment already exist.** This plan
extends that feature; it does not build it from scratch. The backend already has
receipt items, item portions, opt-outs and the apply-to-expense split
(`backend/app/models/receipt_item.py`,
`backend/app/models/receipt_item_portion.py`,
`backend/app/services/receipts.py`,
`backend/app/utils/receipt_split.py`). The UI already has an items review screen
at `/groups/:groupId/expenses/:expenseId/items`
(`frontend/src/pages/group/ReceiptItemsPage.jsx`) where the user can edit items,
assign each item to participants or “Everyone (shared)”, mark opt-outs and apply
the resulting split to the expense. What is missing is discoverability and the
expense-first flow: the route is not linked from the expense card/form, the
receipt image is not shown there, and the create-from-receipt button currently
performs a total-only extraction rather than opening the multi-item flow. §2.4
fixes those gaps without replacing the existing split logic.

**Recommended target model**

- One `Attachment` row per uploaded file: optional `expense_id`, `group_id`,
  filename, content type, size, dimensions, URL, thumbnail URL, storage key and
  optional receipt state.
- Receipt state lives on the same row: status/attempts/provider/model/merchant/
  date/currency/total/raw extraction.
- Receipt items, portions and opt-outs reference `attachment_id` instead of
  `receipt_id`.
- “Scan with AI” transitions an attachment into receipt processing and creates
  its items. Unscanned attachments are ordinary files.
- KEY INFORMATION: We allow the user still to create the expense from the receipt,
  but we also allow the user now to process a receipt uploaded after the expense
  was created.
- The UI has one attachment list. It shows receipt badges/actions on attachments
  that have been scanned, but never asks the user whether something is a
  “document” or a “receipt”.

**What this removes:** the `expense_documents` table and service, the
`Receipt.image_url`/`document_id` duality, the `/documents` and `/receipts/upload`
duplicate upload routes, the duplicate receipt/document extension maps and SSRF
route matchers, two Dexie stores plus their backup/outbox variants, the
`expense_documents`/`receipt_items` feature flags, and the “merge two lists”
serializer/UI logic. The extraction and split algorithms stay as-is.

## 1. AI configuration, documentation and mock mode

### 1.1 Settings

Add to `backend/app/core/config.py` and the env templates:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AI_MOCK` | `false` | Return deterministic local fixtures instead of calling a provider |
| `AI_MOCK_DELAY_MS` | `0` | Optional delay to exercise loading states |
| `AI_RESPONSE_FORMAT` | `auto` | `auto`, `json_schema` or `json_object`; `auto` retries with `json_object` when a provider rejects strict schemas |

Validation:

- `AI_MOCK=true` must be rejected in `ENVIRONMENT=production` (same guard style
  as `ENABLE_MOCK_LOGIN`).
- Log one warning at startup when mock mode is active.
- Do not expose any AI secret through `/api/features` or a `VITE_*` variable.

### 1.2 Mock client

Add `backend/app/services/ai_mock.py` and a separate response file
`backend/app/services/ai_mock_responses.json`:

- The JSON file is the single source of canned responses. Python must not embed
  the fixture objects. It has one top-level key per response name:
  `receipt_response`, `receipt_items_response` and `category_response`.
- Receipt-items fixture: a realistic restaurant bill with 4–5 line items,
  tax/service charge and a total that reconciles exactly.
- Receipt-total fixture: amount, title, today's date (use a `{{today}}` token
  that the loader substitutes, or another explicit date rule), and category `0`.
- Category fixture: `{"categoryId": 0}`.
- `ai_mock.py` loads the JSON once with `json.loads`, validates that all required
  keys exist, implements the same `complete(...)` interface as
  `ChatCompletionClient`, and selects a fixture by `response_format["name"]`.
- `get_ai_client()` returns the mock client when `AI_MOCK=true`; no HTTP client
  is created. Existing `FakeAiClient` tests keep working.
- Tests must load the same JSON and assert that every fixture still parses with
  the real receipt/category parsers, so the file cannot drift from the schema.

### 1.3 Provider compatibility

`ChatCompletionClient.complete()` currently always sends
`response_format.type=json_schema`. Not every OpenAI-compatible provider accepts
that shape. Add a fallback:

1. send `json_schema` as today;
2. on HTTP 400/422 that mentions `response_format`, retry once with
   `{"type": "json_object"}` and a short “reply with JSON only” message;
3. keep the existing defensive parser, which already handles malformed output.

This is important for the DeepSeek example because its OpenAI-compatible API
documents JSON output, not necessarily strict schema mode. Gemini's
OpenAI-compatible endpoint supports schema-style structured output. Add tests
for both the strict-schema request and the fallback.

### 1.4 README

Add a “Receipt scanning with AI” section covering:

- the server-only variables: `AI_API_KEY`, `AI_BASE_URL`, the three model
  variables, feature flags and limits;
- Gemini example using the OpenAI-compatible endpoint
  `https://generativelanguage.googleapis.com/v1beta/openai/` and a current
  vision-capable model such as `gemini-3.8-flash`;
- DeepSeek example using `https://api.deepseek.com` and a vision-capable model
  such as `deepseek-flash` (not `deepseek-v4-pro`, which does not accept vision
  input);
- a note that the model must accept image input; a text-only model can only be
  used for category inference;
- **development**: `./dev` enables the receipt AI/category flags and mock login.
  Attachments themselves are always on. Add `AI_MOCK=true` to `.env` or run
  `AI_MOCK=true ./dev` to test the complete flow with no key. Document the dev
  mock-login request for testing the authenticated AI endpoints;
- **production**: AI flags default to off. Set `ENABLE_RECEIPT_AI` /
  `ENABLE_CATEGORY_EXTRACT` explicitly, set a real key/base URL/model, and never
  enable `AI_MOCK` or `ENABLE_MOCK_LOGIN`. The API key belongs in the server
  `.env`/secret store, not `VITE_*`;
- a cost/security warning: every real extraction attempt is a paid model call,
  retries are capped by `RECEIPT_MAX_ATTEMPTS`, and uploads are AI rate-limited.

Mirror the relevant comments in `.env.example` and
`.env.production.example`. Add a deployment/README test if the existing
`test_deployment.py` pattern requires documented settings to stay in sync.

### 1.5 Usage flow

The README should also briefly explain the two supported flows:

1. **Receipt first**: attach a receipt image/PDF on the new-expense form, let the
   AI fill title/amount/date/category, then save and review line items.
2. **Expense first**: create the expense, open it, attach a file, and click
   “Scan with AI” to extract items and open the smart-split review.

## 2. One attachment experience for receipts and documents

### 2.1 Backend model and API (destructive)

Create one `Attachment` model/table and delete the old split:

- `attachments`: `id`, `group_id`, optional `expense_id`, `storage_key`, `url`,
  `filename`, `content_type`, `byte_size`, `width`, `height`, `thumbnail_url`,
  optional receipt state (`receipt_status`, `attempts`, `raw_extraction`,
  `provider`, `model`, `merchant`, `receipt_date`, `currency_code`, `total`),
  plus sync columns.
- `group_id` is required so a receipt can be uploaded before the expense exists.
  `expense_id` is nullable until the expense is created/linked.
- Deleting an expense deletes its attachments and their rows/files. Do not keep
  the old orphan-document behavior; it is only extra state to maintain.
- At most one attachment per expense may carry receipt processing state (partial
  unique index on `expense_id` where `receipt_status IS NOT NULL`); other files
  remain ordinary attachments. This preserves the current “one receipt split per
  expense” model without preventing multiple files.
- Rename `ReceiptItem`/`ReceiptItemPortion`/`ReceiptOptOut` to
  `AttachmentItem`/`AttachmentItemPortion`/`AttachmentOptOut`, with
  `attachment_id` replacing `receipt_id`. Keep the pure receipt split and
  extraction utilities; only the owner changes.
- Merge `backend/app/services/documents.py` and the upload/state parts of
  `receipts.py` into `backend/app/services/attachments.py`. Remove
  `expense_document.py`, `receipt.py` and the duplicated document service.
- Replace `ExpenseRead.documents` and `ExpenseRead.receipt` with
  `ExpenseRead.attachments: AttachmentRead[]`. Do not keep compatibility fields.

API surface:

- `POST /groups/{group_id}/attachments` — multipart upload, optional
  `expense_id`; accepts images and PDFs. This is the only upload route.
- `GET /groups/{group_id}/attachments/{attachment_id}` — attachment metadata.
- `GET /groups/{group_id}/attachments/{attachment_id}/file` — original bytes.
- `GET /groups/{group_id}/attachments/{attachment_id}/thumbnail` — thumbnail.
- `PATCH /groups/{group_id}/attachments/{attachment_id}` — link/unlink an
  expense (used after “receipt first” creation).
- `DELETE /groups/{group_id}/attachments/{attachment_id}`.
- `POST /groups/{group_id}/attachments/{attachment_id}/extract-total`.
- `POST /groups/{group_id}/attachments/{attachment_id}/extract-items` — optional
  `expense_id` to link while extracting.
- `GET /groups/{group_id}/attachments/{attachment_id}/receipt` — receipt state
  (`items`, `opt_outs`, `split`).
- Item/portion/opt-out/apply routes move under the same attachment resource.
- Delete the old `/receipts/upload`, `/receipts/images/...`, `/documents`,
  `/receipts/extract-total`, `/receipts/extract-items` and related routes.

Simplified feature flags:

- Attachments are always available; delete `ENABLE_EXPENSE_DOCUMENTS`.
- Replace `ENABLE_RECEIPT_EXTRACT` + `ENABLE_RECEIPT_ITEMS` with one
  `ENABLE_RECEIPT_AI` flag.
- Keep `ENABLE_CATEGORY_EXTRACT` (or rename it consistently to
  `ENABLE_CATEGORY_AI`) for text-only category inference.
- `/api/features` becomes `{receipt_ai, category_ai}`; remove
  `expense_documents` and `receipt_items` from the frontend contract.

Destructive migration/reset:

- One Alembic revision drops `expense_documents`, `receipts`, `receipt_items`,
  `receipt_item_portions` and `receipt_opt_outs`, then creates `attachments`,
  `attachment_items`, `attachment_item_portions` and `attachment_opt_outs`.
  No data copy and no backward-compatible dual-read path.
- Update the legacy importer to read old Prisma tables into the new attachment
  rows; this keeps fixture/import tests useful without keeping the runtime split.
- Bump the Dexie schema version and drop/recreate the local document/receipt
  tables as `attachments` and children. Because there is no production data, do
  not write a complex IndexedDB backfill; clear the old app data on upgrade.
- New storage keys use `attachments/{group_id}/{attachment_id}.{ext}` and
  `attachments/{group_id}/{attachment_id}.thumb.jpg`. Old dev upload directories
  can be deleted.

### 2.2 Frontend: thumbnails and full-screen preview

Create `frontend/src/components/attachments/`:

- `AttachmentList` / `AttachmentCard` — one list used by the expense create and
  edit forms.
- `AttachmentPreviewDialog` — full-screen preview:
  - images: `<img>` with `object-contain`;
  - PDFs: no inline preview; show the filename/icon with an “Open in a new
    tab” link;
  - accessible title, close button, Escape handling.
- Thumbnails:
  - image attachments use the already-compressed image with CSS
    `object-fit: cover`;
  - PDFs use a PDF icon plus filename.
- Replace `ExpenseDocumentsCard` with the attachment list while keeping the
  notes/reimbursement fields. Do not render document IDs as the visible label;
  show filename/type/size and a pending-upload badge.
- Show the receipt thumbnail and a “Scan with AI” action on the expense edit
  page, not only on the dedicated items route.

For receipts uploaded before an expense exists, render a local preview from
the stored blob/Dexie placeholder as soon as the file is selected, so the user
never uploads a file and sees nothing.

### 2.3 Compression and PDF support

- Add one shared `prepareUpload(file)` helper used by the single attachment
  upload:
  - images: compress with configurable env values (defaults: max dimension 1600,
    JPEG quality 0.82) and `imageDimensions`;
  - PDFs: do not recompress; enforce the size limit and read page count.
- Expose the compression settings as Vite env variables
  (`VITE_IMAGE_MAX_DIMENSION`, `VITE_IMAGE_QUALITY`) with the defaults above.
- Update the file inputs to `accept="image/*,application/pdf"`.
- Backend:
  - add `application/pdf` to `UPLOAD_ALLOWED_TYPES`;
  - add `.pdf` to the attachment extension/content-type maps;
  - validate the actual file signature (JPEG/PNG/WebP `%PDF`) instead of trusting
    only the browser-provided MIME type;
  - serve PDFs with `Content-Disposition: inline` and the correct media type.
- PDFs are attachments only for now: no server-side rasterization, no PDF
  thumbnail and no AI extraction from a PDF. The UI shows an “Open in a new tab”
  link instead. This keeps the dependency surface small; images are the primary
  receipt format.

### 2.4 The two expense flows

**Receipt first (existing flow, fixed end-to-end)**

- Keep the “Create expense from receipt” button on the create form.
- Upload creates one group-scoped `Attachment` (no expense yet) and returns its
  `attachment_id` plus preview/thumbnail data.
- After the expense is created, `PATCH` that attachment with the new
  `expense_id`. Then offer “Assign receipt items”.
- If the user only asked for a total, persist the attachment link without forcing
  a paid item extraction; “Assign items” can run item extraction later.

**Expense first (new flow)**

- On the expense edit page, every attachment has “Scan with AI”.
- It calls `POST /attachments/{attachment_id}/extract-items` with the current
  `expense_id`, then navigates to
  `/groups/:groupId/expenses/:expenseId/items`.
- The existing items page remains the review/apply screen; add a visible link to
  it from `ExpenseCard` (receipt icon/paperclip) and from the edit form when an
  attachment has receipt state.
- If receipt AI is disabled, “Scan with AI” is hidden and the attachment remains
  a normal viewable file. Attachments themselves are never feature-gated.

## 3. Activity attribution and the active user

### Root cause

`CreateGroup` currently writes `setActiveUser(group.id, null)`. That marks the
group as “active user already answered”, so `GroupLayout` never opens the
“Who are you?” dialog on a newly created group. The expense form then sends no
`participant_id`, and the activity row has a null participant, which the UI
renders as “Someone”.

### Fix

- Remove the `setActiveUser(group.id, null)` special case. A newly created group
  should follow the same first-visit flow as any other group.
- Keep the choice in localStorage only; no `UserGroup` column, migration or sync
  change. This is the human-approved scope.
- In `GroupLayout`, preselect the participant whose normalized name matches the
  signed-in account name when possible, but still show the dialog for explicit
  confirmation. Guests keep the plain picker.
- Ensure every expense create/update/delete and group update sends
  `participant_id` from the resolved active user. If the user explicitly chose
  “I don’t want to select anyone”, keep that choice and show “Someone” only then.
- Keep client-side participant lookup for display names; do not add a second
  actor-name source.

### Tests

- Creating a group and opening it shows the active-user dialog (or preselects a
  matching account participant), unlike today.
- Selecting a participant and creating an expense makes Activity show that
  participant’s name, not “Someone”.
- Declining to select anyone still behaves as an explicit “nobody” choice.
- No account/sync migration is required.

## 4. Hide the Information tab when empty

- Compute the tab list in `GroupHeader` from the group instead of using the
  static `TABS` array.
- Filter out `Information` when `group.information` is null, empty or
  whitespace-only. Keep Settings, where information is edited.
- If a user is already on `/information` when it becomes empty, show the normal
  empty state or redirect to `/expenses`; direct URLs should still not crash.
- Add a component/E2E test for both empty and non-empty groups.

### 4.1 Remove the Montreal/Quebec attribution

- Replace `Footer.madeIn` in `frontend/src/locales/messages/en-US.json` with the
  Zurich/Switzerland attribution: “Made in Zurich, Switzerland 🇨🇭”.
- Update every other locale that still contains “Montréal/Montreal/Quebec” with
  the same attribution (translated if the locale already translates the line,
  otherwise the English text is acceptable).
- The footer currently uses `Footer.madeIn`; keep the i18n key and only change
  the value so no component change is required.
- Add/update a Footer test if the locale sync test does not already cover it.

## 5. Cross-cutting updates

Documentation and contracts:

- `README.md`: AI setup, dev/prod difference, mock flag, both upload flows,
  PDF support.
- `.env.example`, `.env.production.example`: new AI mock/format settings, PDF
  upload type, the collapsed `ENABLE_RECEIPT_AI` flag, the image compression
  settings, and removal of `ENABLE_EXPENSE_DOCUMENTS` / `ENABLE_RECEIPT_ITEMS`.
- `docs/api.md`, `docs/openapi.json`: replace the old receipt/document routes
  with the attachment routes, PDF support and the new `ExpenseRead.attachments`
  shape.
- `docs/repository-contract.md`: replace `receipts.*`/`documents.*` with
  `attachments.*` and the new upload/extraction arguments.
- `docs/offline-capabilities.md`: PDF queue behavior, thumbnail/preview behavior,
  and the rule that mock mode is server-side and online-only.
- `docs/security.md`: confirm AI mock cannot run in production, PDF rendering
  limits and magic-byte validation.

Database/offline:

- One destructive Alembic revision: drop the old receipt/document tables,
  create `attachments` and child tables, and remove the old sync entries.
- Bump the Dexie schema and replace the old `documents`/`receipt*` stores with
  `attachments`/`attachmentItems`/`attachmentPortions`/`attachmentOptOuts`.
  Clear old local data instead of writing a migration for data that does not
  exist in production.
- Replace the outbox entity types `document_upload`/`receipt_upload` with one
  `attachment_upload`; update backup/restore to the new table names.
- Verify `verifyDatabaseCompatibility()` and bundle-size checks still pass.

## 6. Suggested delivery order

1. **Quick wins / trust fixes**
   - active-user root cause and Information tab;
   - receipt thumbnail + full-screen preview;
   - compression for attachment uploads.
2. **AI usability**
   - `AI_MOCK`, README Gemini/DeepSeek examples, response-format fallback;
   - dev mock-login documentation.
3. **Destructive attachment unification**
   - new `Attachment` model/table and destructive migration;
   - one upload/download/preview/extraction API;
   - PDF upload/preview, thumbnails and compression;
   - create-from-receipt linking and expense-first “Scan with AI”;
   - Dexie/outbox/backup cleanup.
4. **Footer and locale cleanup**
   - replace the Montreal/Quebec attribution in all locales.
5. **Hardening**
   - magic-byte validation, cleanup semantics, OpenAPI/README/coverage updates.

## 7. Verification plan

Backend:

```bash
cd backend
PYTHONPATH=. .venv/bin/pytest -n auto
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

Add or extend:

- `tests/test_ai.py`: mock client, production guard, JSON-mode fallback.
- Replace `tests/test_receipts.py` with `tests/test_attachments.py`: upload,
  PDF download, magic-byte rejection, expense linking, thumbnail metadata,
  delete cleanup.
- `tests/test_activities_api.py`: participant attribution.
- `tests/test_deployment.py`: env/README settings stay documented.
- Migration tests: destructive upgrade produces only the new attachment tables,
  and the legacy importer targets them.

Frontend:

```bash
cd frontend
npm test -- --run
npm run lint
npm run typecheck
npx playwright test
```

Add or extend:

- `ExpenseForm` / attachment component tests for compressed image upload, PDF
  selection, thumbnail rendering and the image preview dialog.
- `GroupHeader` test for the conditional Information tab.
- `active-user` E2E: new group asks/confirms, activity shows the name.
- `attachments` E2E: create-from-receipt links the attachment; create-first then
  “Scan with AI” opens the items page; image preview opens full-screen; PDF opens
  via its link.
- Footer/locale test for the Zurich attribution.

## 8. Resolved decisions

1. Active user stays local in localStorage; no account-linked participant.
2. PDFs are attachment-only: no inline preview, no thumbnail, no AI extraction.
   They open through a normal link.
3. Images are compressed in the browser before upload; the compressed image is
   the only copy the application keeps.
4. Compression parameters are env-configurable with defaults of 1600 px and
   0.82 quality.

## Round 2 plan

Status: implemented in the same change set as the Round 1 follow-up.

| Review item | Fix |
| --- | --- |
| Items were only visible after saving the receipt | Online receipt-first scans now extract line items immediately and show a read-only preview in the expense form. Saving opens the assign-items screen directly. |
| “Review items” should be called “Assign items” and appear near advanced splitting | Renamed the attachment action and added a second button next to “Advanced splitting options” whenever the expense has a scanned receipt. |
| Assigning an item to two people failed with “Attachment not found” | Attachment mutations now recover a missing local row with one server bootstrap before failing; snapshot races are ignored. |
| Applying the receipt should return to the previous screen | The items page navigates back after a successful apply, falling back to the expense editor for direct links. |
| The itemized AI summary sometimes disappeared | Expense sync changes no longer delete receipt items when their attachment remains; only removed attachments are cleaned up. Stale bootstrap responses cannot overwrite newer local attachments. |
| Dev-console `startTime` TypeError | Incomplete Chromium resource-timing entries are filtered before React's Suspense image bandwidth estimator reads them. |

### Verification additions

- `ReceiptItemsPreview` shows extracted items before save.
- `AttachmentList` and the expense form expose “Assign items”.
- `applySyncChange` preserves receipt items for an updated expense and cleans them up only when the attachment is gone.
- `bootstrapGroup` ignores an older snapshot that resolves after a newer one.
