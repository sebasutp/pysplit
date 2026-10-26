import type { Page } from '@playwright/test'

import { expect, test } from './fixtures'

/**
 * The normal dev suite runs on :5173 where PWA dev mode is off, so these specs
 * skip there. When the suite targets the production preview (:4173) or
 * `PWA_E2E=1` is set, a missing manifest/worker is a failure, not a skip.
 */
export const REQUIRE_PRODUCTION_PWA =
  process.env.PWA_E2E === '1' ||
  /:4173(?:\/|$)/.test(process.env.BASE_URL || process.env.E2E_BASE_URL || '')

export async function productionPwa(page: Page): Promise<boolean> {
  await page.goto('/groups')
  const hasManifest = (await page.locator('link[rel="manifest"]').count()) > 0
  if (!hasManifest) return false
  try {
    await page.waitForFunction(
      async () => {
        if (!('serviceWorker' in navigator)) return false
        const registration = await navigator.serviceWorker.getRegistration()
        return registration?.active?.state === 'activated'
      },
      null,
      { timeout: 10_000 },
    )
  } catch {
    return false
  }
  return true
}

/** Skip on the dev server, but fail when a production PWA build was promised. */
export async function requireProductionPwa(page: Page): Promise<void> {
  const ready = await productionPwa(page)
  if (ready) return
  test.skip(!REQUIRE_PRODUCTION_PWA, 'requires a production PWA build')
  expect(ready, 'production PWA build expected on this BASE_URL').toBe(true)
}

/** Reload until the active worker controls this page (first install is not claimed). */
export async function ensureController(page: Page): Promise<boolean> {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.reload()
    try {
      await page.waitForFunction(
        () => Boolean(navigator.serviceWorker?.controller),
        null,
        { timeout: 5_000 },
      )
      return true
    } catch {
      // The first reload can race activation; try again.
    }
  }
  return false
}
