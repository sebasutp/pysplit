#!/usr/bin/env node
/**
 * Copy the reference locale files into the SPA and fill missing keys from
 * en-US. The migrated application enforces an identical key set in every
 * locale (see `scripts/check_architecture.py`), so partial translations are
 * completed with the English text rather than left with holes.
 *
 * Usage: node scripts/sync-locales.mjs [reference-messages-dir]
 */
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const defaultSource = resolve(here, '../../spliit/messages')
const source = resolve(process.argv[2] || defaultSource)
const target = resolve(here, '../src/locales/messages')

/** @param {Record<string, unknown>} value @param {Record<string, unknown>} template @returns {Record<string, unknown>} */
function keepKnown(value, template) {
  const result = {}
  for (const [key, baseValue] of Object.entries(template)) {
    if (!(key in value)) {
      result[key] = baseValue
      continue
    }
    const child = value[key]
    if (
      baseValue &&
      typeof baseValue === 'object' &&
      !Array.isArray(baseValue) &&
      child &&
      typeof child === 'object' &&
      !Array.isArray(child)
    ) {
      result[key] = keepKnown(
        /** @type {Record<string, unknown>} */ (child),
        /** @type {Record<string, unknown>} */ (baseValue),
      )
    } else {
      result[key] = child
    }
  }
  return result
}

const files = (await readdir(source)).filter((name) => name.endsWith('.json')).sort()
const base = JSON.parse(await readFile(join(source, 'en-US.json'), 'utf8'))

await mkdir(target, { recursive: true })
for (const file of files) {
  const messages = JSON.parse(await readFile(join(source, file), 'utf8'))
  const merged = keepKnown(messages, base)
  await writeFile(join(target, file), `${JSON.stringify(merged, null, 2)}\n`)
}

console.log(`Synced ${files.length} locale files from ${source}`)
