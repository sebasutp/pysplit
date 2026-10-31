/**
 * Frontend runtime configuration.
 *
 * Only this module reads `import.meta.env`. Everything else imports the
 * resolved values, so tests can mock `services/config.js` instead of the
 * bundler environment.
 */

/** @type {string} */
const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api'

/** Base URL without a trailing slash. @type {string} */
export const API_BASE_URL = configuredBaseUrl.replace(/\/+$/, '')

/** @type {string} */
export const APP_NAME = import.meta.env.VITE_APP_NAME || 'pysplit'

/** @type {boolean} */
export const IS_DEV = Boolean(import.meta.env.DEV)

/** Image upload compression settings. */
const dimension = Number(import.meta.env.VITE_IMAGE_MAX_DIMENSION || 1600)
const quality = Number(import.meta.env.VITE_IMAGE_QUALITY || 0.82)
export const IMAGE_MAX_DIMENSION = Number.isFinite(dimension) && dimension > 0 ? dimension : 1600
export const IMAGE_QUALITY =
  Number.isFinite(quality) && quality > 0 && quality <= 1 ? quality : 0.82
