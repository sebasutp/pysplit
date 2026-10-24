# Legacy balance fixtures

These JSON files are generated from the **reference** implementation
(`spliit/src/lib/balances.ts::getBalances`) and replay the exact balances of the
confirmed legacy databases. `backend/scripts/verify_import.py` matches them by
the SHA-256 checksum of the source database file.

Expenses are read exactly as stored. The generator does not call
`createRecurringExpenses`: the import is a row-for-row copy, and the verifier
must compare the dataset it actually copied. The edge fixture's open recurrence
is due in 2099, so even a reference read would not materialise new frames.

| File | Source | Checksum |
|---|---|---|
| `balances-spliit-data.json` | `spliit/spliit-data/spliit.db` (6 groups) | `ef53ca0d…` |
| `balances-spliit.json` | `spliit/spliit.db` (296 groups) | `53ffee7f…` |
| `balances-legacy-fixture.json` | `backend/tests/fixtures/legacy/legacy_fixture.db` | `04d55380…` |

Regenerate (the reference tree is read-only, so the generator lives in the
backend and runs against the reference's `node_modules`/`tsconfig`):

```bash
cd spliit
NODE_PATH="$PWD/node_modules" \
DATABASE_URL=file:/absolute/path/to/legacy.db \
TS_NODE_PROJECT=tsconfig.json \
node -r ts-node/register/transpile-only -r tsconfig-paths/register \
  ../backend/scripts/reference/export-legacy-balances.ts \
  --source /absolute/path/to/legacy.db \
  --out ../shared/fixtures/legacy/balances-<name>.json
```

The small fixture database is rebuilt deterministically with:

```bash
cd backend
python tests/fixtures/legacy/build_fixture.py
```
