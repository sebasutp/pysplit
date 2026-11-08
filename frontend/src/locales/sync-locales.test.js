import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import process from 'node:process'

import { afterEach, describe, expect, it } from 'vitest'

const script = join(process.cwd(), 'scripts', 'sync-locales.mjs')
/** @type {string[]} */
const roots = []

/**
 * @param {string} directory
 * @param {string} name
 * @param {unknown} value
 */
function writeJson(directory, name, value) {
  writeFileSync(join(directory, name), `${JSON.stringify(value, null, 2)}\n`)
}

/**
 * @param {Record<string, unknown>} app
 * @param {Record<string, unknown>} upstream
 * @returns {{target: string, source: string}}
 */
function fixture(app, upstream) {
  const root = mkdtempSync(join(tmpdir(), 'pysplit-locales-'))
  roots.push(root)
  const target = join(root, 'app')
  const source = join(root, 'upstream')
  mkdirSync(target, { recursive: true })
  mkdirSync(source, { recursive: true })
  for (const [name, value] of Object.entries(app)) writeJson(target, name, value)
  for (const [name, value] of Object.entries(upstream)) writeJson(source, name, value)
  return { target, source }
}

/**
 * @param {string[]} args
 */
function run(args) {
  return spawnSync(process.execPath, [script, ...args], { encoding: 'utf8' })
}

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

describe('sync-locales', () => {
  it('keeps reviewed app translations by default', () => {
    const { target, source } = fixture(
      {
        'en-US.json': {
          A: {
            translated: 'Hello',
            placeholder: 'Same',
            missing: 'Missing',
            empty: 'Empty',
            appOnly: 'Custom',
            customised: 'Custom English',
          },
          B: 'English',
        },
        'de-DE.json': {
          A: {
            translated: 'Hallo alt',
            placeholder: 'Eigen',
            empty: '',
            appOnly: 'Custom',
            customised: 'Eigene Übersetzung',
          },
          B: 'Deutsch',
          Extra: 'Zusatz',
        },
      },
      {
        'en-US.json': {
          A: {
            translated: 'Hello',
            placeholder: 'Same',
            missing: 'Missing',
            empty: 'Empty',
            customised: 'Upstream English',
          },
          B: 'English',
        },
        'de-DE.json': {
          A: {
            translated: 'Hallo neu',
            placeholder: 'Same',
            missing: 'Fehlt',
            empty: 'Leer',
            customised: 'Upstream Übersetzung',
          },
          B: 'Deutsch',
        },
      },
    )

    const result = run([source, '--target', target])
    expect(result.status).toBe(0)

    expect(JSON.parse(readFileSync(join(target, 'de-DE.json'), 'utf8'))).toEqual({
      A: {
        // A reviewed app translation always wins over upstream.
        translated: 'Hallo alt',
        placeholder: 'Eigen',
        // Missing and empty app values are filled from upstream.
        missing: 'Fehlt',
        empty: 'Leer',
        appOnly: 'Custom',
        // The app en-US source changed, so the upstream translation is stale.
        customised: 'Eigene Übersetzung',
      },
      B: 'Deutsch',
      Extra: 'Zusatz',
    })
  })

  it('--prefer-upstream restores upstream-first merging', () => {
    const { target, source } = fixture(
      {
        'en-US.json': { Greeting: 'Hello' },
        'de-DE.json': { Greeting: 'Hallo alt' },
      },
      {
        'en-US.json': { Greeting: 'Hello' },
        'de-DE.json': { Greeting: 'Hallo neu' },
      },
    )

    const result = run([source, '--target', target, '--prefer-upstream'])
    expect(result.status).toBe(0)
    expect(JSON.parse(readFileSync(join(target, 'de-DE.json'), 'utf8'))).toEqual({
      Greeting: 'Hallo neu',
    })
  })

  it('ignores upstream translations that drop placeholders or markup', () => {
    const { target, source } = fixture(
      {
        'en-US.json': {
          Activity: 'Expense <em>{expense}</em> created',
          Invite: 'Join with {code}',
        },
        'de-DE.json': {
          Activity: 'Expense <em>{expense}</em> created',
          Invite: 'Join with {code}',
        },
      },
      {
        'en-US.json': {
          Activity: 'Expense <em>{expense}</em> created',
          Invite: 'Join with {code}',
        },
        'de-DE.json': {
          Activity: 'Ausgabe {expense} erstellt',
          Invite: 'Beitreten',
        },
      },
    )

    const result = run([source, '--target', target])
    expect(result.status).toBe(0)
    expect(JSON.parse(readFileSync(join(target, 'de-DE.json'), 'utf8'))).toEqual({
      // The upstream values dropped <em> and {code}, so English is safer.
      Activity: 'Expense <em>{expense}</em> created',
      Invite: 'Join with {code}',
    })
  })

  it('falls back to en-US, follows its order and writes formatted JSON', () => {
    const { target, source } = fixture(
      {
        'en-US.json': { Z: 'Zed', A: 'Ay', Nested: { second: 'Second', first: 'First' } },
        'de-DE.json': {},
      },
      {
        'en-US.json': { Z: 'Zed', A: 'Ay' },
        'de-DE.json': { Z: 'Zed', A: 'Ay' },
      },
    )

    const result = run([source, '--target', target])
    expect(result.status).toBe(0)

    const written = readFileSync(join(target, 'de-DE.json'), 'utf8')
    expect(written.endsWith('\n')).toBe(true)
    expect(written).toContain('\n  "Z": "Zed"')
    expect(Object.keys(JSON.parse(written))).toEqual(['Z', 'A', 'Nested'])
  })

  it('--check reports stale files without writing them', () => {
    const { target, source } = fixture(
      {
        'en-US.json': { Greeting: 'Hello' },
        'de-DE.json': { Greeting: 'Hello' },
      },
      {
        'en-US.json': { Greeting: 'Hello' },
        'de-DE.json': { Greeting: 'Hallo' },
      },
    )

    const stale = run([source, '--target', target, '--check'])
    expect(stale.status).toBe(1)
    expect(stale.stderr).toContain('de-DE.json')
    expect(JSON.parse(readFileSync(join(target, 'de-DE.json'), 'utf8'))).toEqual({
      Greeting: 'Hello',
    })

    expect(run([source, '--target', target]).status).toBe(0)
    const fresh = run([source, '--target', target, '--check'])
    expect(fresh.status).toBe(0)
    expect(fresh.stdout).toContain('Would update 0/1 locale file(s)')
  })

  it('--check accepts a reviewed app translation that differs from upstream', () => {
    const { target, source } = fixture(
      {
        'en-US.json': { Greeting: 'Hello' },
        'de-DE.json': { Greeting: 'Hallo alt' },
      },
      {
        'en-US.json': { Greeting: 'Hello' },
        'de-DE.json': { Greeting: 'Hallo neu' },
      },
    )

    const result = run([source, '--target', target, '--check'])
    expect(result.status).toBe(0)
    expect(result.stdout).toContain('Would update 0/1 locale file(s)')
    expect(JSON.parse(readFileSync(join(target, 'de-DE.json'), 'utf8'))).toEqual({
      Greeting: 'Hallo alt',
    })
  })

  it('fails clearly when the upstream directory is absent', () => {
    const { target } = fixture({ 'en-US.json': { Greeting: 'Hello' }, 'de-DE.json': {} }, {})

    const result = run([join(target, 'missing'), '--target', target])
    expect(result.status).toBe(1)
    expect(result.stderr).toContain('Upstream messages not found')
  })
})
