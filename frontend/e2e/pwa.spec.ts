import { expect, test } from './fixtures'
import { ensureController, requireProductionPwa } from './pwa-helpers'

/**
 * These assertions need the generated service worker, so they run against a
 * production build (`npm run build && npx vite preview --port 4173`) and skip
 * in the normal Vite dev suite where PWA dev mode is disabled. On :4173 (or
 * with PWA_E2E=1) a missing manifest or inactive worker fails the suite.
 */

test('ships an installable manifest with masks, shortcuts and icons', async ({ page }) => {
  await requireProductionPwa(page)

  const response = await page.request.get('/manifest.webmanifest')
  expect(response.ok()).toBe(true)
  const manifest = await response.json()
  expect(manifest.start_url).toBe('/groups')
  expect(manifest.scope).toBe('/')
  expect(manifest.display).toBe('standalone')
  expect(manifest.theme_color).toBe('#0b7a5b')
  expect(manifest.background_color).toBe('#ffffff')
  expect(manifest.icons.map((icon) => icon.sizes)).toEqual(
    expect.arrayContaining(['192x192', '512x512']),
  )
  expect(manifest.icons.some((icon) => icon.purpose === 'maskable')).toBe(true)
  expect(manifest.shortcuts.map((shortcut) => shortcut.url)).toContain('/groups')

  for (const icon of manifest.icons) {
    const iconResponse = await page.request.get(icon.src)
    expect(iconResponse.ok(), icon.src).toBe(true)
  }
})

test('precaches the shell and never stores API responses in Workbox caches', async ({ page }) => {
  await requireProductionPwa(page)

  // The first install does not control the page because clientsClaim is off.
  expect(await ensureController(page)).toBe(true)

  await page.evaluate(async () => {
    await fetch('/api/health').catch(() => {})
  })

  const caches = await page.evaluate(async () => {
    const names = await window.caches.keys()
    const entries = []
    for (const name of names) {
      const cache = await window.caches.open(name)
      for (const request of await cache.keys()) entries.push(request.url)
    }
    return { names, entries }
  })

  expect(caches.names.some((name) => name.includes('workbox-precache'))).toBe(true)
  expect(caches.entries.some((url) => url.includes('/index.html'))).toBe(true)
  expect(caches.entries.some((url) => url.includes('/icons/icon-192.png'))).toBe(true)
  expect(caches.entries.filter((url) => new URL(url).pathname.startsWith('/api/'))).toEqual([])
})

test('boots the SPA shell for an unknown deep link while offline', async ({ page }) => {
  await requireProductionPwa(page)
  expect(await ensureController(page)).toBe(true)

  await page.context().setOffline(true)
  try {
    await page.goto('/groups/offline-unknown/expenses')
    await expect(page.getByRole('link', { name: 'pysplit' })).toBeVisible({ timeout: 20_000 })
    await expect(page.getByRole('main')).toBeVisible()
  } finally {
    await page.context().setOffline(false)
  }
})
