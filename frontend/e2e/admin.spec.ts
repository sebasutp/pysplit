import { signInAsAdmin, signInAsCreator } from './app'
import { expect, test } from './fixtures'

function uniqueEmailSuffix(): string {
  return Math.random().toString(36).slice(2, 8)
}

test('shows metrics and pre-authorizes a user', async ({ page }) => {
  await signInAsAdmin(page)
  await page.goto('/admin')

  await expect(
    page.getByRole('heading', { name: 'Administration Dashboard', exact: true }),
  ).toBeVisible()
  await expect(page.getByText('Registered Users')).toBeVisible()
  await expect(page.getByText('Total Groups')).toBeVisible()

  const email = `preauth-${uniqueEmailSuffix()}@example.com`
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByRole('button', { name: 'Pre-authorize', exact: true }).click()

  await expect(page.getByText(email, { exact: true })).toBeVisible({ timeout: 15_000 })
})

test('denies non-admin accounts', async ({ page }) => {
  await signInAsCreator(page)
  await page.goto('/admin')

  await expect(page.getByText('Access Denied')).toBeVisible()
  await expect(
    page.getByRole('link', { name: 'Return to My Groups' }),
  ).toBeVisible()
})
