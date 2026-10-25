import { expect, Locator, Page } from '@playwright/test'

/**
 * Generic UI primitives. These exist to absorb three recurring hazards in this
 * app: React's first render and async data loads racing the first interaction,
 * the custom Select rendering its options inline, and Intl emitting glyphs that
 * vary by ICU build.
 */

export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Formats an amount exactly as the app does -- see formatCurrency in
 * src/utils/currency.js, which builds an Intl.NumberFormat with the group
 * currency. Never hardcode '$30.00' in a spec; call money(30).
 */
export function money(
  amount: number,
  currency = 'USD',
  locale = 'en-US',
): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

/**
 * Fills a controlled React input and proves the value stuck.
 *
 * Form fields are plain useState-controlled inputs whose initial value can be
 * replaced when the group/expense data finishes loading. A fill that lands too
 * early is silently reverted, so retry until the value survives.
 */
export async function fillStable(input: Locator, value: string): Promise<void> {
  await expect(async () => {
    await input.fill(value)
    await expect(input).toHaveValue(value, { timeout: 1000 })
  }).toPass({ timeout: 20_000 })
}

/**
 * Picks an option from the custom Select (src/components/ui/Select.jsx).
 *
 * The trigger is a role="combobox" button and the options render inline under
 * role="option" only while the menu is open; the trigger may not respond until
 * async data has loaded. Re-opening on each attempt handles both. Pass a regex
 * for any label containing a non-ASCII glyph (the split modes use an en dash).
 */
export async function selectRadixOption(
  page: Page,
  trigger: Locator,
  option: string | RegExp,
): Promise<void> {
  await expect(async () => {
    const choice = page.getByRole('option', { name: option }).first()
    const alreadyOpen = await choice.isVisible().catch(() => false)
    if (!alreadyOpen) await trigger.click({ timeout: 5_000 })
    await choice.click({ timeout: 5_000 })
  }).toPass({ timeout: 20_000 })
}

/**
 * Sets a participant checkbox: a native <input type="checkbox"> that also
 * mirrors its state to aria-checked. Playwright's check() is more brittle
 * against the React-controlled row than reading the attribute and clicking
 * only when it differs.
 */
export async function setChecked(
  checkbox: Locator,
  checked: boolean,
): Promise<void> {
  await expect(async () => {
    const state = await checkbox.getAttribute('aria-checked')
    if ((state === 'true') !== checked) await checkbox.click({ timeout: 5_000 })
    expect(await checkbox.getAttribute('aria-checked')).toBe(String(checked))
  }).toPass({ timeout: 15_000 })
}

/**
 * The <Card> whose CardTitle (an h3) is `title`. Balances and Suggested
 * reimbursements are two structurally identical, unlabelled cards, so
 * assertions have to be scoped to one of them.
 */
export function cardByTitle(page: Page, title: string): Locator {
  return page
    .getByRole('heading', { name: title, exact: true })
    .locator('xpath=../..')
}

/**
 * The field wrapper <div> around the <label> with this exact text, so a spec
 * can scope a combobox (or another control) by its visible label regardless of
 * the generated element ids.
 */
export function fieldByLabel(page: Page, label: string): Locator {
  return page
    .locator('label')
    .filter({ hasText: new RegExp(`^${escapeRegExp(label)}$`) })
    .locator('xpath=..')
}

/** Retries `action` until `settled` succeeds -- for clicks that precede a route/render update. */
export async function clickUntil(
  action: () => Promise<void>,
  settled: () => Promise<void>,
): Promise<void> {
  await expect(async () => {
    await action()
    await settled()
  }).toPass({ timeout: 20_000 })
}
