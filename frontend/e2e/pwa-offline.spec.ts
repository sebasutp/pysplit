import { expect, test } from './fixtures'
import { ensureController, requireProductionPwa } from './pwa-helpers'

const GROUP_ID = 'offline-cached-group'

/**
 * Write a fully cached group straight into the IndexedDB stores Dexie created.
 * This keeps the offline test independent of the API (the gate serves dist
 * with a static server and no backend proxy).
 */
async function seedCachedGroup(page) {
  await page.evaluate(
    async ({ groupId }) => {
      const database = await new Promise((resolve, reject) => {
        const request = indexedDB.open('pysplit')
        request.onsuccess = () => resolve(request.result)
        request.onerror = () => reject(request.error)
      })
      const timestamp = '2026-01-01T00:00:00.000Z'
      await new Promise((resolve, reject) => {
        const transaction = database.transaction(
          ['groups', 'participants', 'outbox'],
          'readwrite',
        )
        transaction.oncomplete = () => resolve(undefined)
        transaction.onerror = () => reject(transaction.error)
        transaction.objectStore('groups').put({
          id: groupId,
          name: 'Offline cached group',
          information: null,
          currency: '$',
          currency_code: 'USD',
          created_at: timestamp,
          updated_at: timestamp,
          version: 1,
          deleted_at: null,
          cached_at: timestamp,
          list_only: false,
        })
        transaction.objectStore('participants').put({
          id: 'offline-alice',
          group_id: groupId,
          name: 'Alice',
          position: 0,
          created_at: timestamp,
          updated_at: timestamp,
          version: 1,
          deleted_at: null,
        })
        transaction.objectStore('outbox').add({
          op_id: 'offline-pending-op',
          group_id: groupId,
          entity_type: 'expense',
          entity_id: 'offline-pending-expense',
          op_type: 'create',
          base_version: null,
          payload: { title: 'Queued dinner' },
          client_time: timestamp,
          status: 'pending',
          attempts: 0,
          next_attempt_at: timestamp,
          last_error: null,
          transport: 'sync',
          meta: {},
          created_at: timestamp,
          updated_at: timestamp,
        })
      })
      database.close()
    },
    { groupId: GROUP_ID },
  )
}

test('boots a cached group from the service worker while offline', async ({ page }) => {
  await requireProductionPwa(page)

  expect(await ensureController(page)).toBe(true)
  await seedCachedGroup(page)

  await page.context().setOffline(true)
  try {
    await page.goto(`/groups/${GROUP_ID}/expenses`)
    await expect(
      page.getByRole('heading', { name: 'Offline cached group' }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(page.getByTestId('sync-status')).toContainText(/Offline/i)
    await expect(page.getByTestId('sync-status')).toContainText(/1 change/i)

    // Pending writes survive a full offline reload; they are not tied to the
    // in-memory page instance.
    await page.reload()
    await expect(
      page.getByRole('heading', { name: 'Offline cached group' }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(page.getByTestId('sync-status')).toContainText(/1 change/i)
  } finally {
    await page.context().setOffline(false)
  }
})
