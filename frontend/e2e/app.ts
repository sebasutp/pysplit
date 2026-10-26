import { expect, Locator, Page } from '@playwright/test'
import {
  clickUntil,
  escapeRegExp,
  fieldByLabel,
  fillStable,
  money,
  selectRadixOption,
  setChecked,
} from './ui'

export type SplitMode = 'EVENLY' | 'BY_SHARES' | 'BY_PERCENTAGE' | 'BY_AMOUNT'

export type Recurrence = 'None' | 'Daily' | 'Weekly' | 'Monthly'

export type GroupTab =
  'Expenses' | 'Balances' | 'Information' | 'Stats' | 'Activity' | 'Settings'

const TAB_PATHS: Record<GroupTab, string> = {
  Expenses: 'expenses',
  Balances: 'balances',
  Information: 'information',
  Stats: 'stats',
  Activity: 'activity',
  Settings: 'edit',
}

// Regexes, not literals: the labels are "Unevenly – By shares" with an en dash.
const SPLIT_MODE_LABELS: Record<SplitMode, RegExp> = {
  EVENLY: /^Evenly$/,
  BY_SHARES: /By shares/,
  BY_PERCENTAGE: /By percentage/,
  BY_AMOUNT: /By amount/,
}

/** GroupForm ships with three participant rows pre-filled (John / Jane / Jack). */
const PREFILLED_PARTICIPANTS = 3

/**
 * The expenses list URL.
 *
 * Anchored deliberately: an unanchored /groups/<id>/expenses also matches
 * /groups/<id>/expenses/create, so waiting on it would return instantly while
 * still sitting on the form and let assertions run before the write landed.
 */
export const EXPENSES_URL = /\/groups\/[^/]+\/expenses(\?|$)/

/** Short random suffix so group names are unique on the shared database. */
export function uniqueSuffix(): string {
  return Math.random().toString(36).slice(2, 8)
}

/**
 * Development-only login used by the migrated suite. Group creation requires
 * the `group_creators` tier, unlike upstream Spliit which had no accounts.
 */
export async function signInAsTier(
  page: Page,
  tier: 'sync_users' | 'group_creators' | 'admin',
  email: string,
  name: string,
): Promise<void> {
  if (!page.url().startsWith('http')) await page.goto('/groups')
  // Let the unauthenticated boot finish before creating a session. Otherwise
  // its in-flight refresh can rotate the cookie after mock-login and make the
  // reload look like refresh-token reuse.
  await expect(
    page.getByRole('button', { name: /^(Sign in|User menu)$/ }),
  ).toBeVisible({ timeout: 20_000 })
  const origin = process.env.BASE_URL ?? process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173'
  const response = await page.request.post('/api/auth/mock-login', {
    headers: { Origin: origin },
    data: { email, name, tier },
  })
  expect(response.ok()).toBeTruthy()
  await page
    .evaluate((value) => window.localStorage.setItem('e2e-authenticated', value), tier)
    .catch(() => {})
  // Reload and wait for the session boot to finish. Navigating away while the
  // refresh request is still in flight can abort the response after the server
  // rotated the token, which would make the next load look like token reuse.
  await page.reload()
  await expect(page.getByRole('button', { name: 'User menu' })).toBeVisible({
    timeout: 20_000,
  })
}

export async function signInAsCreator(page: Page): Promise<void> {
  if (!page.url().startsWith('http')) await page.goto('/groups')
  const alreadySignedIn = await page
    .evaluate(() => window.localStorage.getItem('e2e-authenticated') === 'group_creators')
    .catch(() => false)
  if (alreadySignedIn) return
  await signInAsTier(page, 'group_creators', 'e2e-creator@example.com', 'E2E Creator')
}

export async function signInAsAdmin(page: Page): Promise<void> {
  if (!page.url().startsWith('http')) await page.goto('/groups')
  await signInAsTier(page, 'admin', 'e2e-admin@example.com', 'E2E Admin')
}

export async function createGroup(
  page: Page,
  opts: { name: string; participants: string[] },
): Promise<string> {
  await signInAsCreator(page)
  await page.goto('/groups/create')

  // fillStable doubles as the render gate: once React keeps a value, the
  // controlled input is live and later clicks are safe.
  await fillStable(page.locator('input[name="name"]'), opts.name)

  for (let i = PREFILLED_PARTICIPANTS; i < opts.participants.length; i++) {
    await page.getByRole('button', { name: 'Add participant' }).click()
    await expect(
      page.locator(`input[name="participants.${i}.name"]`),
    ).toBeVisible()
  }

  // Drop surplus rows from the end, so the remaining indices never shift.
  for (let i = PREFILLED_PARTICIPANTS - 1; i >= opts.participants.length; i--) {
    const row = page
      .locator('li')
      .filter({ has: page.locator(`input[name="participants.${i}.name"]`) })
    await row.getByRole('button').click()
    await expect(
      page.locator(`input[name="participants.${i}.name"]`),
    ).toHaveCount(0)
  }

  for (let i = 0; i < opts.participants.length; i++) {
    await fillStable(
      page.locator(`input[name="participants.${i}.name"]`),
      opts.participants[i],
    )
  }

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  await page.waitForURL(EXPENSES_URL, { timeout: 30_000 })

  const groupId = /\/groups\/([^/]+)\/expenses/.exec(page.url())
  if (!groupId) throw new Error(`Could not read group id from ${page.url()}`)
  return groupId[1]
}

/**
 * Seeds an expense through the public group API.
 *
 * Stage 8A has no expense form yet, but the global-balance card is in scope and
 * must be exercised end to end. UI-driven expense creation replaces this helper
 * once Stage 8B lands (the reference `addExpense` remains available).
 */
export async function addExpenseViaApi(
  page: Page,
  groupId: string,
  expense: {
    title: string
    /** As typed, e.g. '90' or '12.34'. */
    amount: string
    paidBy: string
    paidFor?: string[]
  },
): Promise<void> {
  const groupResponse = await page.request.get(`/api/groups/${groupId}`)
  expect(groupResponse.ok()).toBeTruthy()
  const group = await groupResponse.json()
  const participants = group.participants as { id: string; name: string }[]
  const payer = participants.find((item) => item.name === expense.paidBy)
  if (!payer) throw new Error(`Unknown payer ${expense.paidBy}`)
  const paidForNames = expense.paidFor ?? participants.map((item) => item.name)
  const paidFor = paidForNames.map((name) => {
    const participant = participants.find((item) => item.name === name)
    if (!participant) throw new Error(`Unknown participant ${name}`)
    return { participant_id: participant.id, shares: 1 }
  })

  const response = await page.request.post(`/api/groups/${groupId}/expenses`, {
    data: {
      expense_date: new Date().toISOString().slice(0, 10),
      title: expense.title,
      category_id: 0,
      amount: Math.round(Number(expense.amount) * 100),
      paid_by_id: payer.id,
      split_mode: 'EVENLY',
      recurrence_rule: 'NONE',
      paid_for: paidFor,
    },
  })
  expect(response.ok()).toBeTruthy()
}

export async function addExpense(
  page: Page,
  groupId: string,
  expense: {
    title: string
    /** As typed, e.g. '90' or '12.34'. */
    amount: string
    /** Participant name. */
    paidBy: string
    /** Participant names. Omit to leave every participant checked. */
    paidFor?: string[]
    splitMode?: SplitMode
    /** Participant name -> share value. Set one for every checked participant. */
    shares?: Record<string, string>
    /** YYYY-MM-DD. Defaults to today. */
    date?: string
    /** Visible category name, e.g. 'Groceries'. Defaults to General. */
    category?: string
    /** Visible label: 'None' | 'Daily' | 'Weekly' | 'Monthly'. Defaults to None. */
    recurrence?: Recurrence
  },
): Promise<void> {
  await page.goto(`/groups/${groupId}/expenses/create`)

  // ExpenseCreatePage renders a loading state until the group and categories
  // resolve, so the submit button appearing means the form is data-ready.
  const submit = page.getByRole('button', { name: 'Create', exact: true })
  await expect(submit).toBeVisible({ timeout: 30_000 })

  await fillStable(page.locator('input[name="title"]'), expense.title)
  // Amount before split mode: BY_AMOUNT re-distributes shares whenever the
  // amount changes, which would wipe values set beforehand.
  await fillStable(page.locator('input[name="amount"]'), expense.amount)
  await selectRadixOption(page, page.getByTestId('paid-by'), expense.paidBy)

  if (expense.date) {
    // The date input has no form name binding, so select it by type.
    await fillStable(page.locator('input[type="date"]'), expense.date)
  }

  if (expense.category) {
    // The category picker is the same custom Select: its trigger is
    // role=combobox and its open items are role=option.
    await selectRadixOption(
      page,
      fieldByLabel(page, 'Category').getByRole('combobox'),
      expense.category,
    )
  }

  if (expense.recurrence) {
    await selectRadixOption(
      page,
      fieldByLabel(page, 'Expense Recurrence').getByRole('combobox'),
      expense.recurrence,
    )
  }

  if (expense.paidFor) {
    const wanted = expense.paidFor
    const rows = await page.locator('[data-id]').all()
    for (const row of rows) {
      const label = (await row.innerText()).split('\n')[0].trim()
      const name = label.replace(/\s*\(.*\)$/, '')
      await setChecked(row.getByRole('checkbox'), wanted.indexOf(name) !== -1)
    }
  }

  const splitMode = expense.splitMode ?? 'EVENLY'
  if (splitMode !== 'EVENLY') {
    // The advanced section is conditionally rendered, so the Split mode
    // select does not exist in the DOM until the toggle is opened.
    await page
      .getByRole('button', { name: /Advanced splitting options/ })
      .click()
    await selectRadixOption(
      page,
      page.getByTestId('split-mode'),
      SPLIT_MODE_LABELS[splitMode],
    )
  }

  if (expense.shares) {
    // Set every participant's share, not just the ones being changed: under
    // BY_AMOUNT the form auto-distributes to whoever has not been edited yet.
    const shares = expense.shares
    const names = Object.keys(shares)
    for (const name of names) {
      await fillStable(
        paidForRow(page, name).getByRole('textbox'),
        shares[name],
      )
    }
  }

  await submit.click()
  await page.waitForURL(EXPENSES_URL, { timeout: 30_000 })
}

export async function openTab(page: Page, tab: GroupTab): Promise<void> {
  const path = new RegExp(`/groups/[^/]+/${TAB_PATHS[tab]}(\\?|$)`)
  await clickUntil(
    () => page.getByRole('tab', { name: tab, exact: true }).click(),
    () => page.waitForURL(path, { timeout: 5_000 }),
  )
}

/** Opens an expense for editing. The card is a div with onClick, not a link. */
export async function openExpense(page: Page, title: string): Promise<void> {
  await clickUntil(
    () =>
      page
        .getByTestId('expense-card')
        .filter({ hasText: title })
        .first()
        .click(),
    () => page.waitForURL(/\/expenses\/[^/]+\/edit/, { timeout: 5_000 }),
  )
}

/**
 * A "Paid for" row on the expense form. Scoped by the checkbox's accessible
 * name because the share inputs inside these rows share a duplicated id and
 * carry no name attribute -- the row is the only way to tell them apart.
 */
export function paidForRow(page: Page, participant: string): Locator {
  return page.locator('[data-id]').filter({
    has: page.getByRole('checkbox', {
      name: new RegExp(`^${escapeRegExp(participant)}\\b`),
    }),
  })
}

/**
 * Makes `name` the active user for this group.
 *
 * The browser stores the active user per group in localStorage, so resolve
 * the participant through the public group API and write the canonical
 * `<groupId>-activeUser` key directly.
 */
export async function setActiveUser(
  page: Page,
  groupId: string,
  name: string,
): Promise<void> {
  const response = await page.request.get(`/api/groups/${groupId}`)
  expect(response.ok()).toBeTruthy()
  const group = await response.json()
  const participant = (group.participants as { id: string; name: string }[]).find(
    (item) => item.name === name,
  )
  if (!participant) throw new Error(`Unknown participant ${name}`)

  await page.goto(`/groups/${groupId}/expenses`)
  await page.evaluate(
    ([key, value]) => window.localStorage.setItem(key, value),
    [`${groupId}-activeUser`, participant.id] as const,
  )
}

/** An expense row in the list. */
export function expenseCard(page: Page, title: string): Locator {
  return page.getByTestId('expense-card').filter({ hasText: title })
}

/** YYYY-MM-DD, n days before today. The suite pins the timezone to UTC. */
export function daysAgo(n: number): string {
  const date = new Date()
  date.setUTCDate(date.getUTCDate() - n)
  return date.toISOString().slice(0, 10)
}

export function balanceRow(page: Page, participant: string): Locator {
  return page.locator(
    `[data-testid="balance-row"][data-participant="${participant}"]`,
  )
}

export async function expectBalance(
  page: Page,
  participant: string,
  amount: number,
): Promise<void> {
  await expect(balanceRow(page, participant)).toContainText(money(amount))
}

export function reimbursementRow(
  page: Page,
  from: string,
  to: string,
): Locator {
  return page.locator(
    `[data-testid="reimbursement-row"][data-from="${from}"][data-to="${to}"]`,
  )
}
