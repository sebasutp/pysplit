# Parity report

Generated from `docs/parity-matrix.yml` by
`scripts/check_parity_matrix.py`. Do not edit by hand.

## Summary

- Features: **111** (69 standard, 42 custom)
- Offline classes: online-only=22, queued=12, read-only=32, read-write=45
- Reference pages discovered: 14
- Procedure files discovered: 28
- Jest suites discovered: 30
- Playwright specs discovered: 14

## Stage 1 (4 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| API-HEALTH | standard | `spliit/src/app/api/health/route.ts::GET` | `GET /api/health` | `n/a` | read-only | `backend/tests/test_health.py::test_health` |
| API-HEALTH-LIVE | standard | `spliit/src/app/api/health/liveness/route.ts::GET` | `GET /api/health/liveness` | `n/a` | read-only | `backend/tests/test_health.py::test_liveness` |
| API-HEALTH-READY | standard | `spliit/src/app/api/health/readiness/route.ts::GET` | `GET /api/health/readiness` | `n/a` | read-only | `backend/tests/test_health.py::test_readiness` |
| TEST-ENV | standard | `spliit/src/lib/env.test.ts` | `GET /api/health` | `n/a` | read-only | `backend/tests/test_health.py::test_config_defaults` |

## Stage 3 (3 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| TEST-CURRENCY-CONVERSION | standard | `spliit/src/lib/currency-conversion.test.ts` | `POST /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses/create` | read-only | `backend/tests/test_domain_parity.py::test_currency_conversion` |
| TEST-SHARES | standard | `spliit/src/lib/shares.test.ts` | `POST /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses/create` | read-only | `backend/tests/test_domain_parity.py::test_shares` |
| TEST-TOTALS | standard | `spliit/src/lib/totals.test.ts` | `GET /api/groups/{group_id}/stats` | `/groups/:groupId/stats` | read-only | `backend/tests/test_domain_parity.py::test_totals` |

## Stage 4 (17 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| ADMIN-DELETE-GROUP | custom | `spliit/src/trpc/routers/admin/index.ts::deleteGroup` | `DELETE /api/admin/groups/{group_id}` | `/admin` | online-only | `backend/tests/test_admin.py::test_delete_group` |
| ADMIN-DELETE-USER | custom | `spliit/src/trpc/routers/admin/index.ts::deleteUser` | `DELETE /api/admin/users/{user_id}` | `/admin` | online-only | `backend/tests/test_admin.py::test_delete_user` |
| ADMIN-LIST-GROUPS | custom | `spliit/src/trpc/routers/admin/index.ts::listGroups` | `GET /api/admin/groups` | `/admin` | online-only | `backend/tests/test_admin.py::test_list_groups` |
| ADMIN-LIST-USERS | custom | `spliit/src/trpc/routers/admin/index.ts::listUsers` | `GET /api/admin/users` | `/admin` | online-only | `backend/tests/test_admin.py::test_list_users` |
| ADMIN-METRICS | custom | `spliit/src/trpc/routers/admin/index.ts::getMetrics` | `GET /api/admin/metrics` | `/admin` | online-only | `backend/tests/test_admin.py::test_metrics` |
| ADMIN-PREAUTHORIZE | custom | `spliit/src/trpc/routers/admin/index.ts::preAuthorizeUser` | `POST /api/admin/users/preauthorize` | `/admin` | online-only | `backend/tests/test_admin.py::test_preauthorize_user` |
| ADMIN-UPDATE-TIER | custom | `spliit/src/trpc/routers/admin/index.ts::updateUserTier` | `PATCH /api/admin/users/{user_id}/tier` | `/admin` | online-only | `backend/tests/test_admin.py::test_update_tier` |
| API-AUTH-CALLBACK | custom | `spliit/src/app/api/auth/[...auth]/route.ts::GET callback` | `GET /api/auth/oauth/{provider}/callback` | `/groups` | online-only | `backend/tests/test_auth.py::test_oauth_callback` |
| API-AUTH-MOCK | custom | `spliit/src/app/api/auth/[...auth]/route.ts::POST mock-login` | `POST /api/auth/mock-login` | `/groups` | online-only | `backend/tests/test_auth.py::test_mock_login_dev_only` |
| API-AUTH-SESSION | custom | `spliit/src/app/api/auth/[...auth]/route.ts::GET session` | `GET /api/auth/me` | `/groups` | online-only | `backend/tests/test_auth.py::test_session` |
| API-AUTH-SIGNIN | custom | `spliit/src/app/api/auth/[...auth]/route.ts::GET signin` | `GET /api/auth/oauth/{provider}/start` | `/groups` | online-only | `backend/tests/test_auth.py::test_oauth_start` |
| API-AUTH-SIGNOUT | custom | `spliit/src/app/api/auth/[...auth]/route.ts::POST signout` | `POST /api/auth/logout` | `/groups` | online-only | `backend/tests/test_auth.py::test_logout` |
| AUTH-ME | custom | `spliit/src/trpc/routers/auth/index.ts::me` | `GET /api/auth/me` | `/groups` | online-only | `backend/tests/test_auth.py::test_me` |
| TEST-AUTH-SESSION | standard | `spliit/src/lib/auth/session.test.ts` | `GET /api/auth/me` | `/groups` | online-only | `backend/tests/test_auth.py::test_session_token` |
| TEST-MAKE-ADMIN | custom | `spliit/src/scripts/make-admin.test.ts` | `POST /api/admin/users/preauthorize` | `/admin` | online-only | `backend/tests/test_admin.py::test_bootstrap_cli` |
| TEST-TRPC-ADMIN | custom | `spliit/src/trpc/admin.test.ts` | `GET /api/admin/metrics` | `/admin` | online-only | `backend/tests/test_admin.py::test_admin_router` |
| TEST-TRPC-RBAC | custom | `spliit/src/trpc/rbac.test.ts` | `GET /api/admin/metrics` | `/admin` | online-only | `backend/tests/test_rbac.py::test_tier_matrix` |

## Stage 5A (11 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| GROUP-CREATE | standard | `spliit/src/trpc/routers/groups/create.procedure.ts::createGroupProcedure` | `POST /api/groups` | `/groups/create` | read-write | `backend/tests/test_groups_api.py::test_create_group` |
| GROUP-GET | standard | `spliit/src/trpc/routers/groups/get.procedure.ts::getGroupProcedure` | `GET /api/groups/{group_id}` | `/groups/:groupId` | read-write | `backend/tests/test_groups_api.py::test_get_group` |
| GROUP-GET-DETAILS | standard | `spliit/src/trpc/routers/groups/getDetails.procedure.ts::getGroupDetailsProcedure` | `GET /api/groups/{group_id}/details` | `/groups/:groupId/information` | read-only | `backend/tests/test_groups_api.py::test_group_details` |
| GROUP-LIST | standard | `spliit/src/trpc/routers/groups/list.procedure.ts::listGroupsProcedure` | `GET /api/groups?ids=` | `/groups` | read-write | `backend/tests/test_groups_api.py::test_list_groups` |
| GROUP-RECORD-ACCESS | custom | `spliit/src/trpc/routers/groups/sync.procedure.ts::recordAccessProcedure` | `POST /api/groups/{group_id}/access` | `/groups/:groupId` | queued | `backend/tests/test_group_sync.py::test_record_access` |
| GROUP-REMOVE-MEMBERSHIP | custom | `spliit/src/trpc/routers/groups/sync.procedure.ts::removeUserGroupProcedure` | `DELETE /api/groups/{group_id}/membership` | `/groups` | queued | `backend/tests/test_group_sync.py::test_remove_membership` |
| GROUP-SYNC | custom | `spliit/src/trpc/routers/groups/sync.procedure.ts::syncGroupsProcedure` | `POST /api/groups/sync` | `/groups` | read-write | `backend/tests/test_group_sync.py::test_merge_local_groups` |
| GROUP-TOGGLE-ARCHIVE | custom | `spliit/src/trpc/routers/groups/sync.procedure.ts::toggleArchiveProcedure` | `PATCH /api/groups/{group_id}/membership` | `/groups` | queued | `backend/tests/test_group_sync.py::test_toggle_archive` |
| GROUP-TOGGLE-STAR | custom | `spliit/src/trpc/routers/groups/sync.procedure.ts::toggleStarProcedure` | `PATCH /api/groups/{group_id}/membership` | `/groups` | queued | `backend/tests/test_group_sync.py::test_toggle_star` |
| GROUP-UPDATE | standard | `spliit/src/trpc/routers/groups/update.procedure.ts::updateGroupProcedure` | `PATCH /api/groups/{group_id}` | `/groups/:groupId/edit` | read-write | `backend/tests/test_groups_api.py::test_update_group` |
| TEST-TRPC-GROUPS-SYNC | standard | `spliit/src/trpc/groups-sync.test.ts` | `POST /api/groups/sync` | `/groups` | read-write | `backend/tests/test_group_sync.py::test_sync_router` |

## Stage 5B (5 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| EXP-CREATE | standard | `spliit/src/trpc/routers/groups/expenses/create.procedure.ts::createGroupExpenseProcedure` | `POST /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses/create` | read-write | `backend/tests/test_expenses_api.py::test_create_by_amount`<br>`frontend/e2e/split-modes.spec.ts` |
| EXP-DELETE | standard | `spliit/src/trpc/routers/groups/expenses/delete.procedure.ts::deleteGroupExpenseProcedure` | `DELETE /api/groups/{group_id}/expenses/{expense_id}` | `/groups/:groupId/expenses` | read-write | `backend/tests/test_expenses_api.py::test_delete_expense` |
| EXP-GET | standard | `spliit/src/trpc/routers/groups/expenses/get.procedure.ts::getGroupExpenseProcedure` | `GET /api/groups/{group_id}/expenses/{expense_id}` | `/groups/:groupId/expenses/:expenseId/edit` | read-write | `backend/tests/test_expenses_api.py::test_get_expense` |
| EXP-LIST | standard | `spliit/src/trpc/routers/groups/expenses/list.procedure.ts::listGroupExpensesProcedure` | `GET /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses` | read-write | `backend/tests/test_expenses_api.py::test_list_expenses` |
| EXP-UPDATE | standard | `spliit/src/trpc/routers/groups/expenses/update.procedure.ts::updateGroupExpenseProcedure` | `PATCH /api/groups/{group_id}/expenses/{expense_id}` | `/groups/:groupId/expenses/:expenseId/edit` | read-write | `backend/tests/test_expenses_api.py::test_update_expense`<br>`frontend/e2e/expense-edit-delete.spec.ts` |

## Stage 5C (9 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| ACT-LIST | standard | `spliit/src/trpc/routers/groups/activities/list.procedure.ts::listGroupActivitiesProcedure` | `GET /api/groups/{group_id}/activities` | `/groups/:groupId/activity` | read-only | `backend/tests/test_activities_api.py::test_list_activities` |
| BAL-FOR-USER | standard | `spliit/src/trpc/routers/groups/balances/forUser.procedure.ts::forUserBalancesProcedure` | `GET /api/balances?groups=` | `/groups` | read-only | `backend/tests/test_balances_api.py::test_global_balance`<br>`frontend/e2e/global-balance.spec.ts` |
| BAL-LIST | standard | `spliit/src/trpc/routers/groups/balances/list.procedure.ts::listGroupBalancesProcedure` | `GET /api/groups/{group_id}/balances` | `/groups/:groupId/balances` | read-only | `backend/tests/test_balances_api.py::test_group_balances`<br>`frontend/e2e/reimbursements.spec.ts` |
| CAT-LIST | standard | `spliit/src/trpc/routers/categories/list.procedure.ts::listCategoriesProcedure` | `GET /api/categories` | `/groups/:groupId/expenses/create` | read-only | `backend/tests/test_categories_api.py::test_list_categories` |
| STAT-CATEGORY-EXPENSES | standard | `spliit/src/trpc/routers/groups/stats/category-expenses.procedure.ts::getStatsCategoryExpensesProcedure` | `GET /api/groups/{group_id}/stats/categories/{category_id}/expenses` | `/groups/:groupId/stats` | read-only | `backend/tests/test_stats_api.py::test_category_drilldown`<br>`frontend/e2e/stats-breakdown.spec.ts` |
| STAT-MONTH-EXPENSES | standard | `spliit/src/trpc/routers/groups/stats/month-expenses.procedure.ts::getStatsMonthExpensesProcedure` | `GET /api/groups/{group_id}/stats/months/{month}/expenses` | `/groups/:groupId/stats` | read-only | `backend/tests/test_stats_api.py::test_month_drilldown`<br>`frontend/e2e/stats-breakdown.spec.ts` |
| STAT-OVERVIEW | standard | `spliit/src/trpc/routers/groups/stats/overview.procedure.ts::getStatsOverviewProcedure` | `GET /api/groups/{group_id}/stats` | `/groups/:groupId/stats` | read-only | `backend/tests/test_stats_api.py::test_stats_overview`<br>`frontend/e2e/stats.spec.ts` |
| TEST-BALANCES | standard | `spliit/src/lib/balances.test.ts` | `GET /api/groups/{group_id}/balances` | `/groups/:groupId/balances` | read-only | `backend/tests/test_balances_api.py::test_balance_math` |
| TEST-STATS-RANGE | standard | `spliit/src/app/groups/[groupId]/stats/stats-range.test.ts` | `GET /api/groups/{group_id}/stats` | `/groups/:groupId/stats` | read-only | `backend/tests/test_stats_api.py::test_date_range` |

## Stage 5D (2 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| API-EXPORT-CSV | standard | `spliit/src/app/groups/[groupId]/expenses/export/csv/route.ts::GET` | `GET /api/groups/{group_id}/expenses/export.csv` | `/groups/:groupId/expenses` | read-only | `backend/tests/test_exports.py::test_csv_export` |
| API-EXPORT-JSON | standard | `spliit/src/app/groups/[groupId]/expenses/export/json/route.ts::GET` | `GET /api/groups/{group_id}/expenses/export.json` | `/groups/:groupId/expenses` | read-only | `backend/tests/test_exports.py::test_json_export` |

## Stage 7 (21 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| API-S3-UPLOAD | custom | `spliit/src/app/api/s3-upload/route.ts::POST` | `POST /api/groups/{group_id}/expenses/{expense_id}/documents` | `/groups/:groupId/expenses/create` | queued | `backend/tests/test_receipts.py::test_document_upload` |
| RCPT-ADD-ITEM | custom | `spliit/src/trpc/routers/groups/receipts/add-item.procedure.ts::addGroupReceiptItemProcedure` | `POST /api/groups/{group_id}/receipts/{receipt_id}/items` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipts.py::test_add_item` |
| RCPT-APPLY | custom | `spliit/src/trpc/routers/groups/receipts/apply-to-expense.procedure.ts::applyGroupReceiptToExpenseProcedure` | `POST /api/groups/{group_id}/receipts/{receipt_id}/apply` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipt_apply.py::test_apply_split` |
| RCPT-DELETE-ITEM | custom | `spliit/src/trpc/routers/groups/receipts/delete-item.procedure.ts::deleteGroupReceiptItemProcedure` | `DELETE /api/groups/{group_id}/receipts/{receipt_id}/items/{item_id}` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipts.py::test_delete_item` |
| RCPT-GET | custom | `spliit/src/trpc/routers/groups/receipts/get.procedure.ts::getGroupReceiptProcedure` | `GET /api/groups/{group_id}/receipts/{receipt_id}` | `/groups/:groupId/expenses/:expenseId/items` | queued | `backend/tests/test_receipts.py::test_get_receipt_split` |
| RCPT-LINK | custom | `spliit/src/trpc/routers/groups/receipts/link.procedure.ts::linkGroupReceiptToExpenseProcedure` | `POST /api/groups/{group_id}/receipts/{receipt_id}/link` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipts.py::test_link_receipt` |
| RCPT-SET-OPT-OUT | custom | `spliit/src/trpc/routers/groups/receipts/set-opt-out.procedure.ts::setGroupReceiptOptOutProcedure` | `PUT /api/groups/{group_id}/receipts/{receipt_id}/opt-outs/{participant_id}` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipts.py::test_set_opt_out` |
| RCPT-SET-PORTIONS | custom | `spliit/src/trpc/routers/groups/receipts/set-item-portions.procedure.ts::setGroupReceiptItemPortionsProcedure` | `PUT /api/groups/{group_id}/receipts/{receipt_id}/items/{item_id}/portions` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipts.py::test_set_portions` |
| RCPT-UPDATE-ITEM | custom | `spliit/src/trpc/routers/groups/receipts/update-item.procedure.ts::updateGroupReceiptItemProcedure` | `PATCH /api/groups/{group_id}/receipts/{receipt_id}/items/{item_id}` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipts.py::test_update_item` |
| TEST-AI-CLIENT | custom | `spliit/src/lib/ai/client.test.ts` | `POST /api/ai/receipts/extract` | `/groups/:groupId/expenses/create` | online-only | `backend/tests/test_ai.py::test_ai_config_precedence` |
| TEST-AI-PROMPTS | custom | `spliit/src/lib/ai/prompts.test.ts` | `POST /api/ai/receipts/items` | `/groups/:groupId/expenses/create` | online-only | `backend/tests/test_ai.py::test_prompt_contract` |
| TEST-CREATE-FROM-RECEIPT-BUTTON-ACTIONS | standard | `spliit/src/app/groups/[groupId]/expenses/create-from-receipt-button-actions.test.ts` | `POST /api/groups/{group_id}/receipts/{receipt_id}/apply` | `/groups/:groupId/expenses/create` | read-write | `backend/tests/test_receipt_apply.py::test_apply_from_button` |
| TEST-FEATUREFLAGS | standard | `spliit/src/lib/featureFlags.test.ts` | `GET /api/features` | `/groups/:groupId/expenses/create` | online-only | `backend/tests/test_ai.py::test_feature_flags` |
| TEST-PUBLIC-UPLOAD-URL | standard | `spliit/src/lib/public-upload-url.test.ts` | `POST /api/groups/{group_id}/expenses/{expense_id}/documents` | `/groups/:groupId/expenses/create` | queued | `backend/tests/test_receipts.py::test_public_upload_url` |
| TEST-RECEIPT-APPLY | custom | `spliit/src/lib/receipt-apply.test.ts` | `POST /api/groups/{group_id}/receipts/{receipt_id}/apply` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipt_apply.py::test_apply_invariants` |
| TEST-RECEIPT-DRAFT | custom | `spliit/src/lib/receipt-draft.test.ts` | `POST /api/ai/receipts/items` | `/groups/:groupId/expenses/create` | queued | `backend/tests/test_receipts.py::test_receipt_draft` |
| TEST-RECEIPT-EXTRACTION | custom | `spliit/src/lib/receipt-extraction.test.ts` | `POST /api/ai/receipts/extract` | `/groups/:groupId/expenses/create` | queued | `backend/tests/test_ai.py::test_receipt_extraction` |
| TEST-RECEIPT-SPLIT | custom | `spliit/src/lib/receipt-split.test.ts` | `GET /api/groups/{group_id}/receipts/{receipt_id}` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipts.py::test_provisional_split` |
| TEST-RECEIPTS | custom | `spliit/src/lib/receipts.test.ts` | `GET /api/groups/{group_id}/receipts/{receipt_id}` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipts.py::test_receipt_lifecycle` |
| TEST-TRPC-RECEIPTS | standard | `spliit/src/trpc/receipts.test.ts` | `GET /api/groups/{group_id}/receipts/{receipt_id}` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `backend/tests/test_receipts.py::test_receipt_router` |
| TEST-UPLOADED-IMAGE-URL | standard | `spliit/src/lib/uploaded-image-url.test.ts` | `POST /api/groups/{group_id}/expenses/{expense_id}/documents` | `/groups/:groupId/expenses/create` | queued | `backend/tests/test_receipts.py::test_uploaded_image_url` |

## Stage 8A (7 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| E2E-GROUP-MANAGEMENT | standard | `spliit/e2e/group-management.spec.ts` | `GET /api/groups` | `/groups` | read-write | `frontend/e2e/group-management.spec.ts` |
| PAGE-GROUP-CREATE | standard | `spliit/src/app/groups/create/page.tsx` | `POST /api/groups` | `/groups/create` | read-write | `frontend/e2e/group-management.spec.ts` |
| PAGE-GROUP-REDIRECT | standard | `spliit/src/app/groups/[groupId]/page.tsx` | `GET /api/groups/{group_id}` | `/groups/:groupId` | read-write | `frontend/e2e/core.spec.ts` |
| PAGE-GROUPS | standard | `spliit/src/app/groups/page.tsx` | `GET /api/groups` | `/groups` | read-write | `frontend/e2e/group-management.spec.ts`<br>`frontend/e2e/global-balance.spec.ts` |
| PAGE-HOME | standard | `spliit/src/app/page.tsx` | `GET /api/groups` | `/` | read-only | `frontend/e2e/group-management.spec.ts` |
| TEST-ANALYTICS-ANONYMIZE-PATH | standard | `spliit/src/lib/analytics/anonymize-path.test.ts` | `GET /api/health` | `/groups` | read-only | `frontend/src/lib/analytics.test.js::anonymizes group and expense ids` |
| TEST-FORM | standard | `spliit/src/components/ui/form.test.tsx` | `GET /api/health` | `/groups` | read-only | `frontend/src/components/ui/Form.test.jsx::renders labelled fields` |

## Stage 8B (15 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| E2E-CORE | standard | `spliit/e2e/core.spec.ts` | `GET /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses` | read-write | `frontend/e2e/core.spec.ts` |
| E2E-EXPENSE-EDIT-DELETE | standard | `spliit/e2e/expense-edit-delete.spec.ts` | `PATCH /api/groups/{group_id}/expenses/{expense_id}` | `/groups/:groupId/expenses` | read-write | `frontend/e2e/expense-edit-delete.spec.ts` |
| E2E-EXPENSE-VARIANTS | standard | `spliit/e2e/expense-variants.spec.ts` | `POST /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses/create` | read-write | `frontend/e2e/expense-variants.spec.ts` |
| E2E-MULTI-CURRENCY | standard | `spliit/e2e/multi-currency.spec.ts` | `POST /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses/create` | read-write | `frontend/e2e/multi-currency.spec.ts` |
| E2E-RECURRENCE | standard | `spliit/e2e/recurrence.spec.ts` | `POST /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses/create` | read-write | `frontend/e2e/recurrence.spec.ts` |
| E2E-SPLIT-MODES | standard | `spliit/e2e/split-modes.spec.ts` | `POST /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses/create` | read-write | `frontend/e2e/split-modes.spec.ts` |
| PAGE-EXPENSE-CREATE | standard | `spliit/src/app/groups/[groupId]/expenses/create/page.tsx` | `POST /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses/create` | read-write | `frontend/e2e/split-modes.spec.ts`<br>`frontend/e2e/multi-currency.spec.ts` |
| PAGE-EXPENSE-EDIT | standard | `spliit/src/app/groups/[groupId]/expenses/[expenseId]/edit/page.tsx` | `PATCH /api/groups/{group_id}/expenses/{expense_id}` | `/groups/:groupId/expenses/:expenseId/edit` | read-write | `frontend/e2e/expense-edit-delete.spec.ts` |
| PAGE-GROUP-ACTIVITY | standard | `spliit/src/app/groups/[groupId]/activity/page.tsx` | `GET /api/groups/{group_id}/activities` | `/groups/:groupId/activity` | read-only | `frontend/e2e/group-management.spec.ts` |
| PAGE-GROUP-EDIT | standard | `spliit/src/app/groups/[groupId]/edit/page.tsx` | `PATCH /api/groups/{group_id}` | `/groups/:groupId/edit` | read-write | `frontend/e2e/group-management.spec.ts` |
| PAGE-GROUP-EXPENSES | standard | `spliit/src/app/groups/[groupId]/expenses/page.tsx` | `GET /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses` | read-write | `frontend/e2e/core.spec.ts`<br>`frontend/e2e/expense-variants.spec.ts` |
| PAGE-GROUP-INFO | standard | `spliit/src/app/groups/[groupId]/information/page.tsx` | `GET /api/groups/{group_id}/details` | `/groups/:groupId/information` | read-only | `frontend/e2e/group-management.spec.ts` |
| TEST-DATE-GROUPS | standard | `spliit/src/lib/date-groups.test.ts` | `GET /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses` | read-only | `backend/tests/test_domain_parity.py::test_date_groups` |
| TEST-EXPENSE-FORM-ACTIONS | standard | `spliit/src/components/expense-form-actions.test.ts` | `POST /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses/create` | read-write | `frontend/src/components/expenses/ExpenseForm.test.jsx::saves splitting defaults` |
| TEST-UTILS | standard | `spliit/src/lib/utils.test.ts` | `GET /api/groups/{group_id}/expenses` | `/groups/:groupId/expenses` | read-only | `frontend/src/lib/utils.test.js::formats amounts and dates` |

## Stage 8C (8 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| E2E-ACTIVE-USER | standard | `spliit/e2e/active-user.spec.ts` | `GET /api/groups/{group_id}` | `/groups/:groupId` | read-write | `frontend/e2e/active-user.spec.ts` |
| E2E-GLOBAL-BALANCE | standard | `spliit/e2e/global-balance.spec.ts` | `GET /api/balances?groups=` | `/groups` | read-only | `frontend/e2e/global-balance.spec.ts` |
| E2E-REIMBURSEMENTS | standard | `spliit/e2e/reimbursements.spec.ts` | `GET /api/groups/{group_id}/balances` | `/groups/:groupId/balances` | read-write | `frontend/e2e/reimbursements.spec.ts` |
| E2E-REPAYMENT-CURRENCY | standard | `spliit/e2e/repayment-currency.spec.ts` | `POST /api/groups/{group_id}/expenses` | `/groups/:groupId/balances` | read-write | `frontend/e2e/repayment-currency.spec.ts` |
| E2E-STATS | standard | `spliit/e2e/stats.spec.ts` | `GET /api/groups/{group_id}/stats` | `/groups/:groupId/stats` | read-only | `frontend/e2e/stats.spec.ts` |
| E2E-STATS-BREAKDOWN | standard | `spliit/e2e/stats-breakdown.spec.ts` | `GET /api/groups/{group_id}/stats` | `/groups/:groupId/stats` | read-only | `frontend/e2e/stats-breakdown.spec.ts` |
| PAGE-GROUP-BALANCES | standard | `spliit/src/app/groups/[groupId]/balances/page.tsx` | `GET /api/groups/{group_id}/balances` | `/groups/:groupId/balances` | read-write | `frontend/e2e/reimbursements.spec.ts`<br>`frontend/e2e/repayment-currency.spec.ts` |
| PAGE-GROUP-STATS | standard | `spliit/src/app/groups/[groupId]/stats/page.tsx` | `GET /api/groups/{group_id}/stats` | `/groups/:groupId/stats` | read-only | `frontend/e2e/stats.spec.ts`<br>`frontend/e2e/stats-breakdown.spec.ts` |

## Stage 8D (4 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| PAGE-ADMIN | custom | `spliit/src/app/admin/page.tsx` | `GET /api/admin/metrics` | `/admin` | online-only | `frontend/e2e/admin.spec.ts` |
| PAGE-EXPENSE-ITEMS | custom | `spliit/src/app/groups/[groupId]/expenses/[expenseId]/items/page.tsx` | `GET /api/groups/{group_id}/receipts/{receipt_id}` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `frontend/e2e/receipts.spec.ts` |
| TEST-COMPRESS-IMAGE | standard | `spliit/src/lib/compress-image.test.ts` | `POST /api/groups/{group_id}/expenses/{expense_id}/documents` | `/groups/:groupId/expenses/create` | queued | `frontend/src/lib/compress-image.test.js::compresses large images` |
| TEST-RECEIPT-FOOTER | custom | `spliit/src/app/groups/[groupId]/expenses/[expenseId]/items/receipt-footer.test.tsx` | `GET /api/groups/{group_id}/receipts/{receipt_id}` | `/groups/:groupId/expenses/:expenseId/items` | read-write | `frontend/src/components/receipts/ReceiptFooter.test.jsx::renders provisional totals` |

## Stage 9B (1 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| E2E-OFFLINE-SYNC | standard | `spliit/e2e/offline-sync.spec.ts` | `POST /api/sync/push` | `/groups` | queued | `frontend/e2e/offline-sync.spec.ts` |

## Stage 10A (2 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| E2E-PWA | standard | `spliit/e2e/pwa.spec.ts` | `GET /api/health` | `n/a` | read-only | `frontend/e2e/pwa.spec.ts` |
| E2E-PWA-OFFLINE | standard | `spliit/e2e/pwa-offline.spec.ts` | `GET /api/health` | `n/a` | read-only | `frontend/e2e/pwa-offline.spec.ts` |

## Stage 11 (2 features)

| ID | Class | Reference | Target API | UI | Offline | Tests |
|---|---|---|---|---|---|---|
| E2E-ADMIN | custom | `spliit/e2e/admin.spec.ts` | `GET /api/admin/metrics` | `/admin` | online-only | `frontend/e2e/admin.spec.ts` |
| E2E-GROUP-SYNC | custom | `spliit/e2e/group-sync.spec.ts` | `POST /api/groups/sync` | `/groups` | read-write | `frontend/e2e/group-sync.spec.ts` |
