import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')

/** @param {string} directory @returns {string[]} */
/** @param {string} directory @returns {string[]} */
function files(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name)
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}

/** @param {unknown} value @param {string} [prefix] @returns {string[]} */
function flattenKeys(value, prefix = '') {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [prefix]
  return Object.entries(value).flatMap(([key, child]) =>
    flattenKeys(child, prefix ? `${prefix}.${key}` : key),
  )
}

describe('frontend architecture', () => {
  it('keeps HTTP, Dexie, outbox and sync out of hooks/components/pages', () => {
    const sources = ['components', 'hooks', 'pages']
      .flatMap((directory) => files(join(root, 'src', directory)))
      .concat([join(root, 'src', 'App.jsx'), join(root, 'src', 'router.jsx')])
      .filter((path) => /\.(js|jsx|ts|tsx)$/.test(path))

    const forbidden = /from\s+['"][^'"]*services\/(?:api|db|outbox|sync)(?:\.js)?['"]/
    const offenders = sources.filter((path) => forbidden.test(readFileSync(path, 'utf8')))
    expect(offenders).toEqual([])
  })

  it('keeps every locale on the same key set', () => {
    const directory = join(root, 'src', 'locales', 'messages')
    const locales = readdirSync(directory).filter((name) => name.endsWith('.json'))
    expect(locales.length).toBeGreaterThanOrEqual(35)
    const base = flattenKeys(JSON.parse(readFileSync(join(directory, 'en-US.json'), 'utf8'))).sort()
    for (const locale of locales) {
      const keys = flattenKeys(JSON.parse(readFileSync(join(directory, locale), 'utf8'))).sort()
      expect(keys, `${locale} key parity`).toEqual(base)
    }
  })

  it('has the Stage 8 end-to-end specs', () => {
    const specs = readdirSync(join(root, 'e2e'))
    for (const name of [
      'group-management.spec.ts',
      'global-balance.spec.ts',
      'core.spec.ts',
      'expense-edit-delete.spec.ts',
      'expense-variants.spec.ts',
      'split-modes.spec.ts',
      'multi-currency.spec.ts',
      'recurrence.spec.ts',
      'stats.spec.ts',
      'stats-breakdown.spec.ts',
      'reimbursements.spec.ts',
      'repayment-currency.spec.ts',
      'active-user.spec.ts',
      'receipts.spec.ts',
      'admin.spec.ts',
    ]) {
      expect(specs).toContain(name)
    }
  })
})
