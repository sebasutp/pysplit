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
