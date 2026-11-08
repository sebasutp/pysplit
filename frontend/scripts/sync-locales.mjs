#!/usr/bin/env node
/**
 * Merge upstream Spliit translations into this application's locale files.
 *
 * The application catalogue (`src/locales/messages`) is the source of truth for
 * the key set: it contains app-specific keys that upstream Spliit does not
 * have. For every key in the app `en-US.json`, the default (`--prefer-app`)
 * value is chosen in this order:
 *
 *   1. the value already present in the app locale, when it is a non-empty
 *      string and differs from app en-US (a reviewed translation),
 *   2. the upstream locale value, when the app value is still the English
 *      placeholder (or missing), the app en-US value still matches upstream
 *      en-US (the translation belongs to the current source string), the
 *      upstream value is a real translation, and its placeholder/markup
 *      signature matches,
 *   3. the app en-US value.
 *
 * `--prefer-upstream` restores the old order: a usable upstream translation,
 * then the existing app value, then app en-US.
 *
 * The source-string guard keeps app customisations such as the Zurich footer
 * attribution from being replaced by a stale upstream translation. It also
 * keeps upstream translations that use retired placeholders out of customised
 * messages.
 *
 * This keeps every app-specific key, preserves reviewed translations, and
 * fills in the rest from upstream or English so that `check_architecture` can
 * enforce key parity. Output uses two-space indentation and a trailing newline.
 * `en-US.json` is never rewritten.
 *
 * Usage:
 *   node scripts/sync-locales.mjs [source-dir] [options]
 *
 * Sources, highest priority first:
 *   --source <dir>              explicit upstream messages directory
 *   [source-dir]                positional upstream messages directory
 *   SPLIIT_MESSAGES_DIR         environment variable
 *   frontend/locales-upstream   default vendored snapshot (offline)
 *
 * Options:
 *   --prefer-app                preserve existing app translations (default)
 *   --prefer-upstream           let upstream translations win over app values
 *   --check                     do not write; exit 1 if any file would change
 *   --report                    print the per-locale summary (default)
 *   --target <dir>              app messages directory (mainly for tests)
 *   -h, --help                  show this help
 */
import { existsSync } from 'node:fs'
import { mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const defaultSource = resolve(here, '../locales-upstream')
const defaultTarget = resolve(here, '../src/locales/messages')

const USAGE = `Usage: node scripts/sync-locales.mjs [source-dir] [options]

Merge upstream Spliit translations while preserving app-specific keys and
reviewed app translations.

Options:
  --source <dir>       upstream messages directory (default: frontend/locales-upstream)
  --target <dir>       app messages directory (default: frontend/src/locales/messages)
  --prefer-app         keep app translations; use upstream only for English
                       placeholders or missing keys (default)
  --prefer-upstream    let upstream translations win over app values
  --check              exit 1 if any locale file would change (does not write)
  --report             print per-locale counts (this is also the default)
  -h, --help           show this help

The source directory may also be set with SPLIIT_MESSAGES_DIR.`

/** @param {unknown} value @returns {value is Record<string, unknown>} */
function isMessageObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/**
 * Flatten a nested message catalogue to `{ "a.b.c": leafValue }`.
 * @param {unknown} value
 * @param {string} [prefix]
 * @param {Record<string, unknown>} [out]
 * @returns {Record<string, unknown>}
 */
export function flattenMessages(value, prefix = '', out = {}) {
  if (!isMessageObject(value)) {
    out[prefix] = value
    return out
  }
  for (const [key, child] of Object.entries(value)) {
    flattenMessages(child, prefix ? `${prefix}.${key}` : key, out)
  }
  return out
}

/**
 * Rebuild the catalogue following the app en-US structure and order.
 * @param {Record<string, unknown>} template
 * @param {string} prefix
 * @param {(path: string, fallback: unknown) => unknown} pick
 * @returns {Record<string, unknown>}
 */
function rebuild(template, prefix, pick) {
  /** @type {Record<string, unknown>} */
  const result = {}
  for (const [key, child] of Object.entries(template)) {
    const path = prefix ? `${prefix}.${key}` : key
    result[key] = isMessageObject(child) ? rebuild(child, path, pick) : pick(path, child)
  }
  return result
}

/**
 * Append keys that only exist in the app locale so a malformed/extra catalogue
 * never loses data silently. The parity check still reports them.
 * @param {Record<string, unknown>} result
 * @param {unknown} localeNode
 * @param {unknown} baseNode
 */
function appendExtras(result, localeNode, baseNode) {
  if (!isMessageObject(localeNode)) return
  for (const [key, value] of Object.entries(localeNode)) {
    if (!isMessageObject(baseNode) || !(key in baseNode)) {
      result[key] = value
    } else if (isMessageObject(value) && isMessageObject(baseNode[key])) {
      const child = result[key]
      if (isMessageObject(child)) appendExtras(child, value, baseNode[key])
    }
  }
}

/**
 * Placeholder and markup signature, used to reject upstream translations that
 * dropped or renamed interpolation tokens (for example missing `<em>` tags).
 * @param {unknown} value
 * @returns {string}
 */
function signature(value) {
  if (typeof value !== 'string') return ''
  const tokens = value.match(/\{\{?[^}]+\}?\}|<\/?[a-z][^>]*>/gi) || []
  return tokens.map((token) => token.toLowerCase()).sort().join('|')
}

/**
 * Merge one locale catalogue.
 * @param {Record<string, unknown>} appBase app en-US catalogue
 * @param {Record<string, unknown>} appLocale current app locale catalogue
 * @param {Record<string, unknown>} upstreamBase upstream en-US catalogue
 * @param {Record<string, unknown>} upstreamLocale upstream locale catalogue
 * @param {{preferUpstream?: boolean}} [options]
 * @returns {Record<string, unknown>}
 */
export function mergeLocale(appBase, appLocale, upstreamBase, upstreamLocale, options = {}) {
  const { preferUpstream = false } = options
  const appFlat = flattenMessages(appLocale)
  const upstreamBaseFlat = flattenMessages(upstreamBase)
  const upstreamFlat = flattenMessages(upstreamLocale)

  const merged = rebuild(appBase, '', (path, fallback) => {
    const appValue = appFlat[path]
    const hasAppValue = path in appFlat
    const upstreamValue = upstreamFlat[path]
    const upstreamEnglish = upstreamBaseFlat[path]
    const appIsTranslated =
      typeof appValue === 'string' && appValue.trim() !== '' && appValue !== fallback
    const upstreamIsUsable =
      typeof fallback === 'string' &&
      typeof upstreamEnglish === 'string' &&
      typeof upstreamValue === 'string' &&
      fallback === upstreamEnglish &&
      upstreamValue !== upstreamEnglish &&
      signature(upstreamValue) === signature(fallback)

    if (preferUpstream) {
      if (upstreamIsUsable) return upstreamValue
      if (hasAppValue) return appValue
      return fallback
    }

    if (appIsTranslated) return appValue
    if (upstreamIsUsable) return upstreamValue
    return fallback
  })

  appendExtras(merged, appLocale, appBase)
  return merged
}

/**
 * @param {string[]} argv
 * @returns {{check: boolean, report: boolean, preferUpstream: boolean, source?: string, target?: string, help: boolean}}
 */
function parseArgs(argv) {
  /** @type {{check: boolean, report: boolean, preferUpstream: boolean, source?: string, target?: string, help: boolean}} */
  const options = { check: false, report: false, preferUpstream: false, help: false }
  /** @type {'app' | 'upstream' | null} */
  let preference = null
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--check') {
      options.check = true
    } else if (arg === '--report') {
      options.report = true
    } else if (arg === '--prefer-app') {
      if (preference === 'upstream') {
        throw new Error('Choose either --prefer-app or --prefer-upstream, not both.')
      }
      preference = 'app'
      options.preferUpstream = false
    } else if (arg === '--prefer-upstream') {
      if (preference === 'app') {
        throw new Error('Choose either --prefer-app or --prefer-upstream, not both.')
      }
      preference = 'upstream'
      options.preferUpstream = true
    } else if (arg === '--source') {
      options.source = argv[++index]
      if (!options.source) throw new Error('--source requires a directory')
    } else if (arg.startsWith('--source=')) {
      options.source = arg.slice('--source='.length)
    } else if (arg === '--target') {
      options.target = argv[++index]
      if (!options.target) throw new Error('--target requires a directory')
    } else if (arg.startsWith('--target=')) {
      options.target = arg.slice('--target='.length)
    } else if (arg === '-h' || arg === '--help') {
      options.help = true
    } else if (arg.startsWith('-')) {
      throw new Error(`Unknown option: ${arg}`)
    } else if (options.source) {
      throw new Error(`Unexpected argument: ${arg}`)
    } else {
      options.source = arg
    }
  }
  return options
}

/**
 * @param {string} catalogue
 * @returns {Promise<unknown>}
 */
async function readJson(catalogue) {
  return JSON.parse(await readFile(catalogue, 'utf8'))
}

async function main() {
  const options = parseArgs(process.argv.slice(2))
  if (options.help) {
    console.log(USAGE)
    return 0
  }

  const source = resolve(options.source || process.env.SPLIIT_MESSAGES_DIR || defaultSource)
  const target = resolve(options.target || defaultTarget)
  const sourceBase = join(source, 'en-US.json')
  const targetBase = join(target, 'en-US.json')

  if (!existsSync(sourceBase)) {
    throw new Error(
      `Upstream messages not found at ${sourceBase}. Pass a source directory or set SPLIIT_MESSAGES_DIR.`,
    )
  }
  if (!existsSync(targetBase)) {
    throw new Error(`App en-US catalogue not found at ${targetBase}.`)
  }

  const appBase = /** @type {Record<string, unknown>} */ (await readJson(targetBase))
  const upstreamBase = /** @type {Record<string, unknown>} */ (await readJson(sourceBase))
  const files = (await readdir(target))
    .filter((name) => name.endsWith('.json') && name !== 'en-US.json')
    .sort()

  await mkdir(target, { recursive: true })

  const changed = []
  const summary = []
  for (const file of files) {
    const appLocale = /** @type {Record<string, unknown>} */ (
      await readJson(join(target, file))
    )
    const upstreamFile = join(source, file)
    const upstreamLocale = existsSync(upstreamFile)
      ? /** @type {Record<string, unknown>} */ (await readJson(upstreamFile))
      : {}
    const merged = mergeLocale(appBase, appLocale, upstreamBase, upstreamLocale, {
      preferUpstream: options.preferUpstream,
    })
    const serialized = `${JSON.stringify(merged, null, 2)}\n`
    const current = await readFile(join(target, file), 'utf8')

    if (current !== serialized) {
      changed.push(file)
      if (!options.check) await writeFile(join(target, file), serialized)
    }

    const baseFlat = flattenMessages(appBase)
    const mergedFlat = flattenMessages(merged)
    const paths = Object.keys(baseFlat)
    const translated = paths.filter((path) => mergedFlat[path] !== baseFlat[path]).length
    summary.push({ file, translated, total: paths.length })
  }

  const label = options.check ? 'Would update' : 'Updated'
  console.log(`${label} ${changed.length}/${files.length} locale file(s) from ${source}.`)
  console.log('Values differing from en-US:')
  for (const { file, translated, total } of summary) {
    const percent = total === 0 ? 0 : (translated / total) * 100
    console.log(`  ${file.padEnd(24)} ${String(translated).padStart(3)}/${total} (${percent.toFixed(1)}%)`)
  }

  if (options.check && changed.length > 0) {
    console.error('Locale files are out of date; run `npm run locales:sync`.')
    console.error(changed.map((file) => `  ${file}`).join('\n'))
    return 1
  }
  return 0
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main()
    .then((code) => {
      process.exitCode = code
    })
    .catch((error) => {
      console.error(`sync-locales: ${error instanceof Error ? error.message : String(error)}`)
      process.exitCode = 1
    })
}
