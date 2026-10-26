import {
  addExpense,
  createGroup,
  EXPENSES_URL,
  expenseCard,
  openExpense,
  uniqueSuffix,
} from './app'
import { expect, test } from './fixtures'
import { fillStable } from './ui'

/** Block the API while leaving the Vite-served app shell reachable. */
async function blockApi(page) {
  await page.route('**/api/**', (route) => route.abort())
}

async function unblockApi(page) {
  await page.unroute('**/api/**')
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  const syncNow = page
    .getByTestId('sync-status')
    .getByRole('button', { name: 'Sync now' })
  if (await syncNow.isVisible().catch(() => false)) await syncNow.click()
}

/** Force a synchronization cycle, preferring the visible status action. */
async function syncFromBanner(page) {
  const button = page
    .getByTestId('sync-status')
    .getByRole('button', { name: 'Sync now' })
  if (await button.isVisible().catch(() => false)) {
    await button.click()
    return
  }
  await page.evaluate(async () => {
    const mod = await import('/src/services/repository/index.js')
    await mod.syncNow({ reason: 'e2e', force: true })
  })
}

test('reads a cached group after the API becomes unavailable', async ({ page }) => {
  const groupId = await createGroup(page, {
    name: `E2E Offline Read ${uniqueSuffix()}`,
    participants: ['Alice', 'Bob'],
  })
  await addExpense(page, groupId, {
    title: 'Cached dinner',
    amount: '40',
    paidBy: 'Alice',
  })

  await blockApi(page)
  await page.reload()

  await expect(page.getByRole('heading', { name: /E2E Offline Read/ })).toBeVisible({
    timeout: 20_000,
  })
  await expect(expenseCard(page, 'Cached dinner')).toContainText('$40.00')
  await expect(page.getByTestId('sync-status')).toContainText(/pending|Offline|Sync error/)
})

test('creates and edits an expense offline, survives reload and syncs exactly once', async ({
  page,
}) => {
  const groupId = await createGroup(page, {
    name: `E2E Offline Write ${uniqueSuffix()}`,
    participants: ['Alice', 'Bob'],
  })
  await page.goto(`/groups/${groupId}/expenses`)
  await blockApi(page)

  await addExpense(page, groupId, {
    title: 'Offline lunch',
    amount: '20',
    paidBy: 'Alice',
  })
  await expect(expenseCard(page, 'Offline lunch')).toContainText('Pending sync')

  // Pending writes survive a reload while the API is still unavailable.
  await page.reload()
  await expect(expenseCard(page, 'Offline lunch')).toContainText('Pending sync')

  await openExpense(page, 'Offline lunch')
  await fillStable(page.locator('input[name="title"]'), 'Offline lunch edited')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.waitForURL(EXPENSES_URL, { timeout: 30_000 })
  await expect(expenseCard(page, 'Offline lunch edited')).toContainText('Pending sync')

  await unblockApi(page)

  await expect(expenseCard(page, 'Offline lunch edited')).not.toContainText(
    'Pending sync',
    { timeout: 30_000 },
  )

  const response = await page.request.get(`/api/groups/${groupId}/expenses`)
  expect(response.ok()).toBeTruthy()
  const body = await response.json()
  const matches = body.items.filter(
    (item) => item.title === 'Offline lunch edited',
  )
  expect(matches).toHaveLength(1)
})

test('queues divergent offline edits and resolves the expense conflict explicitly', async ({
  browser,
  page,
}) => {
  const groupId = await createGroup(page, {
    name: `E2E Offline Conflict ${uniqueSuffix()}`,
    participants: ['Alice', 'Bob'],
  })
  await addExpense(page, groupId, {
    title: 'Conflict dinner',
    amount: '50',
    paidBy: 'Alice',
  })

  const secondContext = await browser.newContext({
    baseURL: process.env.BASE_URL ?? 'http://127.0.0.1:5173',
    locale: 'en-US',
    timezoneId: 'UTC',
  })
  await secondContext.addInitScript(() => {
    try {
      window.localStorage.setItem('newGroup-activeUser', 'None')
    } catch {
      // about:blank has no storage.
    }
  })
  const second = await secondContext.newPage()
  await second.goto(`/groups/${groupId}/expenses`)
  await expect(expenseCard(second, 'Conflict dinner')).toBeVisible()

  const expenseResponse = await page.request.get(`/api/groups/${groupId}/expenses`)
  const expenseBody = await expenseResponse.json()
  const expenseId = expenseBody.items[0].id

  // Open both edit forms while the network is still available, then go offline
  // before saving. This keeps the test focused on the outbox conflict, not on
  // client-side routing under a fully offline document origin.
  await page.goto(`/groups/${groupId}/expenses/${expenseId}/edit`)
  await second.goto(`/groups/${groupId}/expenses/${expenseId}/edit`)
  await expect(page.locator('input[name="title"]')).toBeVisible()
  await expect(second.locator('input[name="title"]')).toBeVisible()

  await blockApi(page)
  await blockApi(second)

  await fillStable(page.locator('input[name="title"]'), 'First device edit')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page).toHaveURL(EXPENSES_URL, { timeout: 30_000 })
  await expect
    .poll(
      async () =>
        page.evaluate(async (id) => {
          const { db } = await import('/src/services/db.js')
          return (await db.expenses.get(id))?.title
        }, expenseId),
      { timeout: 10_000 },
    )
    .toBe('First device edit')

  await fillStable(second.locator('input[name="title"]'), 'Second device edit')
  await second.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(second).toHaveURL(EXPENSES_URL, { timeout: 30_000 })
  await expect
    .poll(
      async () =>
        second.evaluate(async (id) => {
          const { db } = await import('/src/services/db.js')
          return (await db.expenses.get(id))?.title
        }, expenseId),
      { timeout: 10_000 },
    )
    .toBe('Second device edit')

  await unblockApi(page)
  await syncFromBanner(page)
  await expect
    .poll(
      async () => {
        const response = await page.request.get(`/api/groups/${groupId}/expenses`)
        const body = await response.json()
        return body.items[0]?.title
      },
      { timeout: 30_000 },
    )
    .toBe('First device edit')

  await unblockApi(second)
  await syncFromBanner(second)
  await expect(second.getByTestId('sync-status')).toContainText(/conflict/i, {
    timeout: 30_000,
  })

  await second.getByRole('button', { name: 'Resolve conflicts' }).click()
  const dialog = second.getByRole('dialog')
  await expect(dialog.getByTestId('conflict-row')).toHaveCount(1)
  await dialog.getByRole('button', { name: 'Keep mine' }).click()
  await expect(dialog.getByTestId('conflict-row')).toHaveCount(0)

  await expect
    .poll(
      async () => {
        const response = await second.request.get(`/api/groups/${groupId}/expenses`)
        const body = await response.json()
        return body.items[0]?.title
      },
      { timeout: 30_000 },
    )
    .toBe('Second device edit')

  await secondContext.close()
})

test('retries a lost push response without duplicating the expense', async ({ page }) => {
  const groupId = await createGroup(page, {
    name: `E2E Offline Retry ${uniqueSuffix()}`,
    participants: ['Alice', 'Bob'],
  })
  await page.goto(`/groups/${groupId}/expenses`)

  let dropped = false
  await page.route('**/api/sync/push', async (route) => {
    if (dropped) {
      await route.continue()
      return
    }
    dropped = true
    await route.fetch()
    await route.fulfill({
      status: 502,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'gateway lost the response' }),
    })
  })

  await addExpense(page, groupId, {
    title: 'Exactly once',
    amount: '25',
    paidBy: 'Bob',
  })
  await expect(expenseCard(page, 'Exactly once')).toContainText('Pending sync')

  await page.unroute('**/api/sync/push')
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await syncFromBanner(page)
  await expect(expenseCard(page, 'Exactly once')).not.toContainText('Pending sync', {
    timeout: 30_000,
  })

  const response = await page.request.get(`/api/groups/${groupId}/expenses`)
  const body = await response.json()
  expect(body.items.filter((item) => item.title === 'Exactly once')).toHaveLength(1)
})
