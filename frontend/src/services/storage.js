/**
 * Storage quota and persistence helpers.
 *
 * Browsers may evict IndexedDB under pressure. The app asks for persistent
 * storage explicitly (only from a user gesture) and surfaces a low-quota
 * warning so the user can export a backup before writes start failing.
 */

const WARNING_RATIO = 0.75
const CRITICAL_RATIO = 0.9

/**
 * @param {number|null|undefined} usage
 * @param {number|null|undefined} quota
 * @returns {'unknown'|'ok'|'warning'|'critical'}
 */
export function quotaLevel(usage, quota) {
  if (!quota || !Number.isFinite(Number(quota)) || Number(quota) <= 0) return 'unknown'
  const ratio = Number(usage || 0) / Number(quota)
  if (ratio >= CRITICAL_RATIO) return 'critical'
  if (ratio >= WARNING_RATIO) return 'warning'
  return 'ok'
}

/**
 * @param {number|null|undefined} bytes
 * @param {string} [locale]
 * @returns {string}
 */
export function formatBytes(bytes, locale = 'en-US') {
  const value = Number(bytes || 0)
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const exponent = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)))
  const amount = value / 1024 ** exponent
  return `${new Intl.NumberFormat(locale, {
    maximumFractionDigits: amount >= 10 || exponent === 0 ? 0 : 1,
  }).format(amount)} ${units[exponent]}`
}

/**
 * @param {{persist?: boolean}} [options]
 * @returns {Promise<{
 *   supported: boolean,
 *   persisted: boolean| null,
 *   usage: number|null,
 *   quota: number|null,
 *   level: 'unknown'|'ok'|'warning'|'critical',
 *   error: string|null,
 * }>}
 */
export async function readStorageStatus(options = {}) {
  if (typeof navigator === 'undefined' || !navigator.storage) {
    return {
      supported: false,
      persisted: null,
      usage: null,
      quota: null,
      level: 'unknown',
      error: null,
    }
  }
  try {
    const persisted =
      typeof navigator.storage.persisted === 'function'
        ? await navigator.storage.persisted()
        : false
    let durable = persisted
    if (!durable && options.persist && typeof navigator.storage.persist === 'function') {
      durable = await navigator.storage.persist()
    }
    const estimate =
      typeof navigator.storage.estimate === 'function'
        ? await navigator.storage.estimate()
        : {}
    const usage = estimate.usage == null ? null : Number(estimate.usage)
    const quota = estimate.quota == null ? null : Number(estimate.quota)
    return {
      supported: true,
      persisted: durable,
      usage,
      quota,
      level: quotaLevel(usage, quota),
      error: null,
    }
  } catch (error) {
    return {
      supported: true,
      persisted: null,
      usage: null,
      quota: null,
      level: 'unknown',
      error: error instanceof Error ? error.message : 'Storage estimate unavailable',
    }
  }
}
