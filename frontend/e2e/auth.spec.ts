import { createGroup, uniqueSuffix } from './app'
import { expect, test } from './fixtures'

const ORIGIN = process.env.BASE_URL ?? process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173'

test('asks anonymous visitors to sign in before creating a group', async ({ page }) => {
  await page.goto('/groups/create')

  await expect(page.getByText('Authentication Required')).toBeVisible()
  await page.getByRole('button', { name: 'Sign in to Create Group' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await expect(page.getByText('Sign in to Spliit')).toBeVisible()
})

test('shows approval messaging for sync users', async ({ page }) => {
  const response = await page.request.post('/api/auth/mock-login', {
    headers: { Origin: ORIGIN },
    data: { email: 'e2e-sync@example.com', name: 'Sync User', tier: 'sync_users' },
  })
  expect(response.ok()).toBeTruthy()

  await page.goto('/groups/create')
  await expect(page.getByText('Group Creation Requires Approval')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Create', exact: true })).toHaveCount(0)
})

test('loads shared group deep links directly', async ({ page }) => {
  const groupId = await createGroup(page, {
    name: `E2E Deep Link ${uniqueSuffix()}`,
    participants: ['Alice', 'Bob'],
  })

  await page.goto(`/groups/${groupId}`)
  await expect(page).toHaveURL(new RegExp(`/groups/${groupId}/expenses$`))
  await expect(page.getByRole('heading', { name: 'Expenses' })).toBeVisible()
})
