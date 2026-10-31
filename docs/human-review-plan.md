# Human review — Round 1 plan

Status: proposed. No implementation has been done yet.

This plan addresses every item in `docs/human-review.md`. It keeps the existing
receipt extraction contract where possible, treats receipts and documents as one
user-facing concept, and adds local-only AI mocking so receipt parsing can be
tested with no API key or provider call.

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

## Decisions and answers

**“Why are receipts and documents separate today?”** Internally they are two
different things:

- a receipt is an AI-processing record with a status, attempts, extracted
  merchant/total/currency, line items, portions, opt-outs and a split;
- an expense document is a generic file attachment.

That distinction is useful for the extraction state machine, but it is not
useful to the user. The plan therefore removes the distinction from the UI and
upload flow, while keeping a receipt as the processing state attached to a file.
We do **not** start by merging the database tables: that would touch sync,
offline Dexie storage, migrations and legacy import in one risky step. Instead,
`ExpenseDocument` remains the file record and `Receipt` becomes the optional
processing state for one of those files. A follow-up can collapse the tables if
the simpler model proves out.

**Recommended target model**

- Every uploaded file is an attachment: image or PDF, with filename, content
  type, dimensions, thumbnail and optional receipt-processing state.
- “Scan with AI” creates/updates the receipt state for that attachment.
- The UI has one attachment list. It shows receipt badges/actions on attachments
  that have been scanned, but never asks the user whether something is a
  “document” or a “receipt”.

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

Add `backend/app/services/ai_mock.py`:

- Implement the same `complete(...)` interface as `ChatCompletionClient`.
- Inspect `response_format["name"]` (`receipt_response`,
  `receipt_items_response`, `category_response`) and return a valid fixture.
- Receipt-items fixture: a realistic restaurant bill with 4–5 line items,
  tax/service charge and a total that reconciles exactly.
- Receipt-total fixture: amount, title, today's date and category `0`.
- Category fixture: `{"categoryId": 0}`.
- `get_ai_client()` returns the mock client when `AI_MOCK=true`; no HTTP client
  is created. Existing `FakeAiClient` tests keep working.

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
- **development**: `./dev` already enables the receipt/document/category flags
  and mock login. Add `AI_MOCK=true` to `.env` or run `AI_MOCK=true ./dev` to
  test the complete flow with no key. Document the dev mock-login request for
  testing the authenticated AI endpoints;
- **production**: flags default to off. Set the feature flags explicitly, set a
  real key/base URL/model, and never enable `AI_MOCK` or `ENABLE_MOCK_LOGIN`.
  The API key belongs in the server `.env`/secret store, not `VITE_*`;
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

### 2.1 Backend model and API

Additive changes first:

- `ExpenseDocument`: add `content_type`, `filename`, `thumbnail_url` (nullable
  for old rows). Add an Alembic migration.
- `Receipt`: add nullable unique `document_id` referencing `expense_documents`
  so a receipt can be tied to a file record rather than only a URL string. Keep
  `image_url` for compatibility with existing receipts and offline placeholders.
- `ExpenseDocumentRead`: return `content_type`, `filename`, `thumbnail_url` and
  an optional `receipt` summary (`id`, `status`).
- Add a single attachment serializer that merges:
  - `expense.documents` (generic files), and
  - a linked `Receipt` row whose `image_url` is not already represented by a
    document.

  Prefer an additive `attachments` array on `ExpenseRead` and keep
  `documents`/`receipt` for one release so older clients and offline code do not
  break.
- Extend receipt extraction input with optional `document_id`. The server
  validates that the document belongs to the same group/expense, then creates or
  links the receipt. Keep `image_url` accepted for the offline queue and legacy
  callers.

New/changed endpoints:

- `POST /groups/{group_id}/expenses/{expense_id}/documents` accepts images and
  PDFs and returns the richer attachment read model.
- `POST /groups/{group_id}/receipts/extract-items` accepts
  `{document_id, expense_id, ...}` in addition to `{image_url, ...}`.
- Deleting an attachment cleans up its linked receipt and item/portion rows in
  the same transaction; deleting an expense keeps its current unlink behavior.
- Document deletion and download must continue to reject cross-group access.

Migration/backfill strategy:

- no destructive merge of `receipts` and `expense_documents`;
- old receipts remain visible because the read model merges the receipt image
  into the attachment list;
- old documents get `content_type`/`filename` inferred from their URL extension
  at read time; a small backfill can populate the columns later;
- a receipt that is already attached to an expense can optionally be backfilled
  into an `expense_documents` row in a one-shot script, but the UI must not
  require it.

### 2.2 Frontend: thumbnails and full-screen preview

Create `frontend/src/components/attachments/`:

- `AttachmentList` / `AttachmentCard` — one list used by the expense create and
  edit forms.
- `AttachmentPreviewDialog` — full-screen preview:
  - images: `<img>` with `object-contain`;
  - PDFs: browser-native `<object type="application/pdf">`/`<iframe>`, plus an
    “Open in a new tab” fallback if the browser blocks embedded PDFs;
  - accessible title, close button, Escape handling.
- Thumbnails:
  - image attachments use the already-compressed image with CSS
    `object-fit: cover`;
  - PDFs use a generated first-page thumbnail (`thumbnail_url`) when available,
    otherwise a clear PDF icon plus filename.
- Replace `ExpenseDocumentsCard` with the attachment list while keeping the
  notes/reimbursement fields. Do not render document IDs as the visible label;
  show filename/type/size and a pending-upload badge.
- Show the receipt thumbnail and a “Scan with AI” action on the expense edit
  page, not only on the dedicated items route.

For receipts uploaded before an expense exists, render a local preview from
the stored blob/Dexie placeholder as soon as the file is selected, so the user
never uploads a file and sees nothing.

### 2.3 Compression and PDF support

- Add one shared `prepareUpload(file)` helper used by both receipt and document
  uploads:
  - images: use the existing `compressImage` defaults (max dimension 1600,
    JPEG quality 0.82) and `imageDimensions`;
  - PDFs: do not recompress; enforce the size limit and read page count.
- Update the file inputs to `accept="image/*,application/pdf"`.
- Backend:
  - add `application/pdf` to `UPLOAD_ALLOWED_TYPES`;
  - add `.pdf` to document/receipt extension maps and content-type maps;
  - validate the actual file signature (JPEG/PNG/WebP `%PDF`) instead of trusting
    only the browser-provided MIME type;
  - serve PDFs with `Content-Disposition: inline` and the correct media type.
- AI extraction from PDFs:
  - add `pymupdf` to `backend/requirements.txt`;
  - rasterize the first page (receipts are normally one page) at a readable DPI
    to PNG/JPEG, then pass that as the existing data URL to the model;
  - cap page count, rasterized dimensions and bytes;
  - if rasterization fails, keep the PDF as a normal attachment but disable AI
    with a clear message rather than failing the whole upload.
- Generate PDF first-page thumbnails at upload time using the same renderer.
  Images can use their compressed original as the thumbnail.

### 2.4 The two expense flows

**Receipt first (existing flow, fixed end-to-end)**

- Keep the “Create expense from receipt” button on the create form.
- Upload creates/returns a receipt identity (new `receipt_id` in the upload
  response is acceptable and additive).
- After the expense is created, link that receipt to it automatically instead
  of leaving an orphaned receipt. Then offer “Review receipt items”.
- If the user only asked for a total, persist the receipt/link without forcing a
  paid item extraction; “Review items” can run item extraction later.

**Expense first (new flow)**

- On the expense edit page, every attachment has “Scan with AI”.
- It calls `extract-items` with the attachment’s `document_id` and the current
  `expense_id`, then navigates to
  `/groups/:groupId/expenses/:expenseId/items`.
- The existing items page remains the review/apply screen; add a visible link to
  it from `ExpenseCard` (receipt icon/paperclip) and from the edit form when a
  receipt exists.
- If the smart-split feature is disabled, “Scan with AI” is hidden and the
  attachment remains a normal viewable file.

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
- In `GroupLayout`, when an account is signed in, preselect the participant
  whose normalized name matches the account name (and, if participant emails
  are added later, the account email). Still show the dialog so the user
  explicitly confirms. For guests, keep the current picker.
- Keep localStorage as the guest/offline fallback, but persist the choice for
  signed-in users:
  - add nullable `active_participant_id` to `UserGroup` (migration `0005`);
  - accept it in the membership update endpoint and include it in group sync;
  - hydrate the active user from the account before falling back to
    localStorage.
  This makes “created by X” follow the account across devices instead of being
  tied to one browser.
- Ensure every expense create/update/delete and group update sends
  `participant_id` from the resolved active user. If the user explicitly chose
  “I don’t want to select anyone”, keep that choice and show “Someone” only then.
- Return actor display names consistently from the API if client-side participant
  lookup is ambiguous, or keep client lookup after the active-user fix; do not
  introduce a second source of truth for names.

### Tests

- Creating a group and opening it shows the active-user dialog (or preselects a
  matching account participant), unlike today.
- Selecting a participant and creating an expense makes Activity show that
  participant’s name, not “Someone”.
- Declining to select anyone still behaves as an explicit “nobody” choice.
- If account persistence is implemented, selecting a participant on one browser
  is restored on a second session.

## 4. Hide the Information tab when empty

- Compute the tab list in `GroupHeader` from the group instead of using the
  static `TABS` array.
- Filter out `Information` when `group.information` is null, empty or
  whitespace-only. Keep Settings, where information is edited.
- If a user is already on `/information` when it becomes empty, show the normal
  empty state or redirect to `/expenses`; direct URLs should still not crash.
- Add a component/E2E test for both empty and non-empty groups.

## 5. Cross-cutting updates

Documentation and contracts:

- `README.md`: AI setup, dev/prod difference, mock flag, both upload flows,
  PDF support.
- `.env.example`, `.env.production.example`: new AI mock/format settings and PDF
  upload type.
- `docs/api.md`, `docs/openapi.json`: new attachment fields, PDF support,
  `document_id` extraction input, richer document read model.
- `docs/repository-contract.md`: attachment read shape and new upload/extraction
  arguments.
- `docs/offline-capabilities.md`: PDF queue behavior, thumbnail/preview behavior,
  and the rule that mock mode is server-side and online-only.
- `docs/security.md`: confirm AI mock cannot run in production, PDF rendering
  limits and magic-byte validation.

Database/offline:

- Alembic migration for `expense_documents.content_type/filename/thumbnail_url`
  and `receipts.document_id`.
- Dexie schema bump with a migration that preserves existing document/receipt
  rows and blobs.
- Verify `verifyDatabaseCompatibility()` and bundle-size checks still pass.

## 6. Suggested delivery order

1. **Quick wins / trust fixes**
   - active-user root cause and Information tab;
   - receipt thumbnail + full-screen preview;
   - compression for document uploads.
2. **AI usability**
   - `AI_MOCK`, README Gemini/DeepSeek examples, response-format fallback;
   - dev mock-login documentation.
3. **Attachment unification**
   - attachment read model, PDF upload/preview, `document_id` extraction;
   - create-from-receipt linking and expense-first “Scan with AI”.
4. **Account-linked active user**
   - `UserGroup.active_participant_id`, migration, sync and cross-device tests.
5. **Hardening**
   - PDF rasterization limits, magic-byte validation, cleanup semantics,
     OpenAPI/README/coverage updates.

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
- `tests/test_receipts.py`: PDF upload/download, magic-byte rejection, document
  linking, thumbnail metadata, delete cleanup.
- `tests/test_activities_api.py`: participant attribution.
- `tests/test_groups_api.py` / sync tests: account active participant.
- `tests/test_deployment.py`: env/README settings stay documented.

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
  selection, thumbnail rendering and preview dialog.
- `GroupHeader` test for the conditional Information tab.
- `active-user` E2E: new group asks/confirms, activity shows the name.
- `receipts` E2E: create-from-receipt links the receipt; create-first then
  “Scan with AI” opens the items page; preview opens full-screen.
- PDF E2E with a small fixture PDF.

## 8. Open questions before implementation

1. Do we want account-linked active users now (`UserGroup.active_participant_id`)
   or only the local first-visit fix in this round? The account link is more work
   but directly addresses “even though I am logged in”.
2. For PDFs, is first-page rasterization enough, or do we need multi-page
   receipts/documents sent to the model?
3. Should the UI keep the full-resolution original when compression is applied,
   or upload only the compressed image (the current receipt behavior)?
4. Should image/PDF compression targets be configurable per deployment, or are
   the current 1600 px / 0.82 defaults acceptable?
