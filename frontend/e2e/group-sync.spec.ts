import {
  addExpenseViaApi,
  createGroup,
  signInAsTier,
  uniqueSuffix,
} from './app'
import { expect, test } from './fixtures'

const ORIGIN =
  process.env.BASE_URL ?? process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173'

/**
 * A second browser profile for the same (or a guest) account.
 *
 * Every context has its own cookies, localStorage and IndexedDB, so two
 * contexts model two devices sharing one server account.
 */
async function openDevice(browser, email, name) {
  const context = await browser.newContext({
    baseURL: ORIGIN,
    locale: 'en-US',
    timezoneId: 'UTC',
  })
  await context.addCookies([{ name: 'NEXT_LOCALE', value: 'en-US', url: ORIGIN }])
  await context.addInitScript(() => {
    try {
      if (!window.localStorage.getItem('newGroup-activeUser')) {
        window.localStorage.setItem('newGroup-activeUser', 'None')
      }
    } catch {
      // about:blank has no storage.
    }
  })
  const page = await context.newPage()
  if (email) await signInAsTier(page, 'group_creators', email, name || 'Sync Device')
  return { context, page }
}

async function forceSync(page) {
  await page.evaluate(async () => {
    const { syncNow } = await import('/src/services/repository/index.js')
    await syncNow({ reason: 'e2e-group-sync', force: true })
  })
}

async function accountGroups(page) {
  return page.evaluate(async () => {
    const { repository } = await import('/src/services/repository/index.js')
    const result = await repository.groups.sync({ groupIds: [] })
    return result?.groups || []
  })
}

function groupCard(page, name) {
  return page.locator('li').filter({ has: page.getByRole('link', { name }) })
}

test('synchronizes a new group and its star state across two devices', async ({
  browser,
  page,
}) => {
  const suffix = uniqueSuffix()
  const email = `group-sync-${suffix}@example.com`
  const name = `Group Sync ${suffix}`

  await signInAsTier(page, 'group_creators', email, name)
  const second = await openDevice(browser, email, name)

  const groupName = `E2E Synced group ${suffix}`
  const groupId = await createGroup(page, {
    name: groupName,
    participants: ['Alice', 'Bob'],
  })

  // Device B discovers the group through the authenticated group scope.
  await expect
    .poll(
      async () =>
        (await accountGroups(second.page)).filter((group) => group.id === groupId).length,
      { timeout: 30_000 },
    )
    .toBe(1)
  await second.page.goto('/groups')
  await expect(second.page.getByRole('link', { name: groupName })).toBeVisible({
    timeout: 30_000,
  })

  // Device A stars it; the membership write is LWW for this user.
  await page.goto('/groups')
  const firstCard = groupCard(page, groupName)
  await firstCard.getByRole('button', { name: 'Star group' }).click()
  await expect(firstCard.getByRole('button', { name: 'Unstar group' })).toBeVisible()
  await forceSync(page)
  await expect
    .poll(async () => {
      const groups = await accountGroups(page)
      return groups.find((group) => group.id === groupId)?.is_starred
    })
    .toBe(true)

  // Device B reloads its synchronized list and sees the same state.
  await second.page.reload()
  await expect(
    groupCard(second.page, groupName).getByRole('button', { name: 'Unstar group' }),
  ).toBeVisible({ timeout: 30_000 })

  await second.context.close()
})

test('removing a group on one device is not undone by another device reload', async ({
  browser,
  page,
}) => {
  const suffix = uniqueSuffix()
  const email = `group-sync-remove-${suffix}@example.com`
  const name = `Group Remove ${suffix}`

  await signInAsTier(page, 'group_creators', email, name)
  const second = await openDevice(browser, email, name)

  const groupName = `E2E Removed group ${suffix}`
  const groupId = await createGroup(page, {
    name: groupName,
    participants: ['Alice', 'Bob'],
  })
  await second.page.goto('/groups')
  await expect(second.page.getByRole('link', { name: groupName })).toBeVisible({
    timeout: 30_000,
  })

  // Device B removes the membership through the group-list menu.
  const secondCard = groupCard(second.page, groupName)
  await secondCard.getByRole('button', { name: 'More options' }).click()
  await second.page
    .getByRole('menuitem', { name: 'Remove from recent groups' })
    .click()
  await expect(second.page.getByRole('link', { name: groupName })).toHaveCount(0)

  // Device A still has the ID in its recent list. Reloading must not turn that
  // stale list read into a new claim for the removed membership.
  await page.reload()
  await expect(page.getByRole('link', { name: groupName })).toHaveCount(0, {
    timeout: 30_000,
  })
  await expect
    .poll(
      async () =>
        (await accountGroups(page)).filter((group) => group.id === groupId).length,
      { timeout: 30_000 },
    )
    .toBe(0)

  await second.context.close()
})

test('claims a guest group on login without duplicating the cache', async ({
  browser,
  page,
}) => {
  const suffix = uniqueSuffix()
  await signInAsTier(
    page,
    'group_creators',
    `group-sync-owner-${suffix}@example.com`,
    'Group Owner',
  )
  const groupName = `E2E Claimed group ${suffix}`
  const groupId = await createGroup(page, {
    name: groupName,
    participants: ['Alice', 'Bob'],
  })
  await addExpenseViaApi(page, groupId, {
    title: 'Claimed dinner',
    amount: '42',
    paidBy: 'Alice',
  })

  // Device B visits the shared link as a guest, so the group is cached without
  // an account membership.
  const guest = await openDevice(browser)
  await guest.page.goto(`/groups/${groupId}/expenses`)
  await expect(guest.page.getByRole('heading', { name: groupName })).toBeVisible({
    timeout: 30_000,
  })
  await expect(guest.page.getByText('Claimed dinner')).toBeVisible({
    timeout: 30_000,
  })

  await signInAsTier(
    guest.page,
    'group_creators',
    `group-sync-claim-${suffix}@example.com`,
    'Guest Claimer',
  )
  await guest.page.goto('/groups')
  await expect(guest.page.getByRole('link', { name: groupName })).toHaveCount(1)

  const counts = await guest.page.evaluate(async (id) => {
    const { db } = await import('/src/services/db.js')
    return {
      groups: await db.groups.count(),
      memberships: await db.userGroups.count(),
      expenses: await db.expenses.where('group_id').equals(id).count(),
    }
  }, groupId)
  expect(counts).toEqual({ groups: 1, memberships: 1, expenses: 1 })

  // A reload keeps exactly one list row: the guest cache was claimed in place.
  await guest.page.reload()
  await expect(guest.page.getByRole('link', { name: groupName })).toHaveCount(1)
  await expect
    .poll(async () => (await accountGroups(guest.page)).filter((group) => group.id === groupId).length)
    .toBe(1)

  await guest.context.close()
})

test('a guest archive cannot leave a star and archive set together', async ({
  browser,
  page,
}) => {
  const suffix = uniqueSuffix()
  const email = `group-sync-flags-${suffix}@example.com`
  const name = `Group Flags ${suffix}`

  await signInAsTier(page, 'group_creators', email, name)
  const groupName = `E2E Flag group ${suffix}`
  const groupId = await createGroup(page, {
    name: groupName,
    participants: ['Alice', 'Bob'],
  })

  await page.goto('/groups')
  const firstCard = groupCard(page, groupName)
  await firstCard.getByRole('button', { name: 'Star group' }).click()
  await expect(firstCard.getByRole('button', { name: 'Unstar group' })).toBeVisible()

  // Device B is a guest that archives the same group, then signs into A's
  // account. The archive claim is positive-only and archive wins over star.
  const guest = await openDevice(browser)
  await guest.page.goto(`/groups/${groupId}/expenses`)
  await expect(guest.page.getByRole('heading', { name: groupName })).toBeVisible({
    timeout: 30_000,
  })
  await guest.page.goto('/groups')
  const guestCard = groupCard(guest.page, groupName)
  await guestCard.getByRole('button', { name: 'More options' }).click()
  await guest.page.getByRole('menuitem', { name: 'Archive group' }).click()
  await guestCard.getByRole('button', { name: 'More options' }).click()
  await expect(
    guest.page.getByRole('menuitem', { name: 'Unarchive group' }),
  ).toBeVisible()
  await guest.page.keyboard.press('Escape')

  await signInAsTier(guest.page, 'group_creators', email, name)
  await expect
    .poll(async () => {
      const group = (await accountGroups(guest.page)).find(
        (item) => item.id === groupId,
      )
      return group && { starred: group.is_starred, archived: group.is_archived }
    })
    .toEqual({ starred: false, archived: true })

  await page.reload()
  const reloadedCard = groupCard(page, groupName)
  await expect(reloadedCard.getByRole('button', { name: 'Star group' })).toBeVisible({
    timeout: 30_000,
  })
  await expect(
    reloadedCard.getByRole('button', { name: 'Unstar group' }),
  ).toHaveCount(0)
  await reloadedCard.getByRole('button', { name: 'More options' }).click()
  await expect(
    page.getByRole('menuitem', { name: 'Unarchive group' }),
  ).toBeVisible()

  await guest.context.close()
})

test('queues an offline login merge and claims the guest group after reconnect', async ({
  browser,
  page,
}) => {
  const suffix = uniqueSuffix()
  await signInAsTier(
    page,
    'group_creators',
    `group-sync-offline-owner-${suffix}@example.com`,
    'Offline Owner',
  )
  const groupName = `E2E Offline claim ${suffix}`
  const groupId = await createGroup(page, {
    name: groupName,
    participants: ['Alice', 'Bob'],
  })

  const guest = await openDevice(browser)
  await guest.page.goto(`/groups/${groupId}/expenses`)
  await expect(guest.page.getByRole('heading', { name: groupName })).toBeVisible({
    timeout: 30_000,
  })

  // Login succeeds, but synchronization is unavailable, so the claim must be
  // queued durably instead of being lost with a transient response.
  await guest.page.route('**/api/sync/**', (route) => route.abort())
  await guest.page.route('**/api/groups/sync', (route) => route.abort())
  await signInAsTier(
    guest.page,
    'group_creators',
    `group-sync-offline-claim-${suffix}@example.com`,
    'Offline Claimer',
  )

  const queued = await guest.page.evaluate(async () => {
    const { db } = await import('/src/services/db.js')
    const marker = await db.metadata.get('pending_group_merge')
    const operations = await db.outbox.toArray()
    return {
      user: marker?.value?.user_id || null,
      claims: operations.filter((row) => row.entity_type === 'user_group').length,
    }
  })
  expect(queued.claims).toBeGreaterThan(0)
  expect(queued.user).toBeTruthy()

  await guest.page.unroute('**/api/sync/**')
  await guest.page.unroute('**/api/groups/sync')
  await forceSync(guest.page)
  await expect
    .poll(
      async () =>
        (await accountGroups(guest.page)).filter((group) => group.id === groupId).length,
      { timeout: 30_000 },
    )
    .toBe(1)

  const marker = await guest.page.evaluate(async () => {
    const { db } = await import('/src/services/db.js')
    return (await db.metadata.get('pending_group_merge'))?.value || null
  })
  expect(marker).toBeNull()

  await guest.page.goto('/groups')
  await expect(guest.page.getByRole('link', { name: groupName })).toHaveCount(1)

  await guest.context.close()
})
