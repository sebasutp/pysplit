/**
 * Generate a reference balance fixture for a legacy database.
 *
 * This is migration tooling, not part of either application. It runs against
 * the checked-out reference source and uses the real `getBalances` function so
 * the Python importer can be compared to the oracle rather than to a second
 * implementation of the same math.
 *
 * The plan names `spliit/scripts/export-legacy-balances.ts`; the reference tree
 * is mounted read-only in this environment, so the script lives here and is
 * executed against `spliit/`'s node_modules/tsconfig:
 *
 *   cd spliit
 *   DATABASE_URL=file:<source> TS_NODE_PROJECT=tsconfig.json \
 *     npx ts-node --transpile-only \
 *     ../backend/scripts/reference/export-legacy-balances.ts \
 *     --source <source> --out <fixture.json>
 */

import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { basename, resolve } from 'node:path'

import Database from 'better-sqlite3'

import { getBalances } from '@/lib/balances'

type LegacyExpense = {
  id: string
  amount: number
  paidBy: { id: string }
  splitMode: string
  paidFor: { participant: { id: string }; shares: number }[]
}

function argument(name: string): string {
  const index = process.argv.indexOf(name)
  if (index === -1 || index === process.argv.length - 1) {
    throw new Error(`missing ${name}`)
  }
  return process.argv[index + 1]
}

const source = resolve(argument('--source'))
const output = resolve(argument('--out'))
const checksum = createHash('sha256').update(readFileSync(source)).digest('hex')

const database = new Database(source, { readonly: true, fileMustExist: true })

// Read stored expenses only. `createRecurringExpenses` is intentionally not
// invoked: the importer copies rows verbatim and verification must compare
// that same dataset.
const groupIds = (
  database.prepare('SELECT id FROM "Group" ORDER BY id').all() as { id: string }[]
).map((row) => row.id)

const expensesByGroup = new Map<string, LegacyExpense[]>()
for (const groupId of groupIds) {
  const expenses = database
    .prepare(
      'SELECT id, amount, paidById, splitMode FROM "Expense" WHERE groupId = ?',
    )
    .all(groupId) as {
    id: string
    amount: number
    paidById: string
    splitMode: string
  }[]

  const paidForStatement = database.prepare(
    'SELECT participantId, shares FROM "ExpensePaidFor" WHERE expenseId = ?',
  )
  expensesByGroup.set(
    groupId,
    expenses.map((expense) => ({
      id: expense.id,
      amount: expense.amount,
      paidBy: { id: expense.paidById },
      splitMode: expense.splitMode,
      paidFor: (
        paidForStatement.all(expense.id) as {
          participantId: string
          shares: number
        }[]
      ).map((row) => ({
        participant: { id: row.participantId },
        shares: row.shares,
      })),
    })),
  )
}

database.close()

const groups: Record<string, ReturnType<typeof getBalances>> = {}
for (const groupId of groupIds) {
  groups[groupId] = getBalances(expensesByGroup.get(groupId) ?? [])
}

writeFileSync(
  output,
  JSON.stringify(
    {
      source: basename(source),
      source_checksum: checksum,
      generated_by: 'spliit/src/lib/balances.ts::getBalances',
      groups,
    },
    null,
    2,
  ) + '\n',
)

console.log(`Wrote ${output} (${groupIds.length} groups, checksum ${checksum})`)
