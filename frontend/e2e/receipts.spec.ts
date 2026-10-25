import { addExpense, createGroup, uniqueSuffix } from './app'
import { expect, test } from './fixtures'

test('opens the smart-split editor and explains when no receipt is linked', async ({
  page,
}) => {
  const groupId = await createGroup(page, {
    name: `E2E Receipt ${uniqueSuffix()}`,
    participants: ['Alice', 'Bob'],
  })
  await addExpense(page, groupId, {
    title: 'Groceries',
    amount: '40',
    paidBy: 'Alice',
  })

  const response = await page.request.get(`/api/groups/${groupId}/expenses?limit=50`)
  expect(response.ok()).toBeTruthy()
  const payload = await response.json()
  const expenseId = payload.items[0].id

  await page.goto(`/groups/${groupId}/expenses/${expenseId}/items`)

  await expect(
    page.getByRole('heading', { name: 'Receipt items', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByText('No receipt is linked to this expense yet.'),
  ).toBeVisible()
  await expect(
    page.getByRole('link', { name: 'Back to expense' }),
  ).toBeVisible()
})

test('shows online-only copy when smart split is disabled', async ({ page }) => {
  const groupId = await createGroup(page, {
    name: `E2E ReceiptDisabled ${uniqueSuffix()}`,
    participants: ['Alice', 'Bob'],
  })
  await addExpense(page, groupId, {
    title: 'Taxi',
    amount: '10',
    paidBy: 'Alice',
  })

  const response = await page.request.get(`/api/groups/${groupId}/expenses?limit=50`)
  const payload = await response.json()
  const expenseId = payload.items[0].id

  await page.route('**/api/features', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        receipt_extract: false,
        receipt_items: false,
        category_extract: false,
        expense_documents: false,
      }),
    }),
  )

  await page.goto(`/groups/${groupId}/expenses/${expenseId}/items`)
  await expect(
    page.getByText(/Smart split is not enabled on this server/),
  ).toBeVisible()
})
