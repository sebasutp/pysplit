/**
 * The single HTTP client.
 *
 * Every request in the application goes through `request()` in this module.
 * Hooks and components must import the repository, not this file (see
 * docs/repository-contract.md). Keeping the transport here means retries,
 * auth headers, error normalisation and cancellation exist in one place.
 */

import { API_BASE_URL } from './config'

/** @typedef {'not_found'|'validation'|'conflict'|'unauthorized'|'forbidden'|'rate_limited'|'network'|'offline_unsupported'|'server'|'aborted'} ErrorCode */

/**
 * @typedef {Object} RequestOptions
 * @property {unknown} [body] JSON-serialisable value, FormData, or string
 * @property {AbortSignal} [signal]
 * @property {Record<string, string>} [headers]
 * @property {boolean} [keepalive]
 */

export class ApiError extends Error {
  /**
   * @param {string} message
   * @param {Object} [options]
   * @param {number|null} [options.status]
   * @param {ErrorCode} [options.code]
   * @param {string} [options.detail]
   * @param {Record<string, unknown>} [options.fields]
   * @param {boolean} [options.retryable]
   */
  constructor(message, options = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status ?? null
    this.code = options.code ?? 'server'
    this.detail = options.detail ?? message
    this.fields = options.fields
    this.retryable = options.retryable ?? false
  }
}

/**
 * DOMException is not an Error subclass in every JS environment, so inspect
 * the name defensively.
 *
 * @param {unknown} error
 * @returns {boolean}
 */
function isAbortError(error) {
  return (
    typeof error === 'object' &&
    error !== null &&
    'name' in error &&
    /** @type {{name?: unknown}} */ (error).name === 'AbortError'
  )
}

/**
 * @param {number} status
 * @returns {ErrorCode}
 */
function codeForStatus(status) {
  if (status === 401) return 'unauthorized'
  if (status === 403) return 'forbidden'
  if (status === 404) return 'not_found'
  if (status === 409) return 'conflict'
  if (status === 422) return 'validation'
  if (status === 429) return 'rate_limited'
  return 'server'
}

/**
 * @param {unknown} value
 * @param {string} fallback
 * @returns {string}
 */
function detailFrom(value, fallback) {
  if (typeof value === 'string' && value) return value
  if (value && typeof value === 'object' && 'detail' in value) {
    const detail = /** @type {{detail: unknown}} */ (value).detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

/**
 * Perform an HTTP request and normalise success/failure.
 *
 * @param {string} path Path beginning with `/` (for example `/health`)
 * @param {string} method
 * @param {RequestOptions} [options]
 * @returns {Promise<unknown>}
 */
async function request(path, method, options = {}) {
  const { body, signal, headers = {}, keepalive = false } = options

  /** @type {Record<string, string>} */
  const requestHeaders = { Accept: 'application/json', ...headers }
  /** @type {BodyInit | undefined} */
  let requestBody

  if (body instanceof FormData) {
    requestBody = body
  } else if (typeof body === 'string') {
    requestBody = body
    requestHeaders['Content-Type'] ??= 'text/plain'
  } else if (body !== undefined) {
    requestBody = JSON.stringify(body)
    requestHeaders['Content-Type'] = 'application/json'
  }

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: requestHeaders,
      ...(requestBody !== undefined ? { body: requestBody } : {}),
      signal,
      keepalive,
      credentials: 'same-origin',
    })
  } catch (error) {
    if (isAbortError(error)) {
      throw new ApiError('Request aborted', { code: 'aborted' })
    }
    throw new ApiError('Network request failed', { code: 'network', retryable: true })
  }

  if (response.status === 204) return undefined

  const contentType = response.headers.get('content-type') || ''
  /** @type {unknown} */
  let payload
  if (contentType.includes('application/json')) {
    payload = await response.json()
  } else {
    payload = await response.text()
  }

  if (!response.ok) {
    const code = codeForStatus(response.status)
    const detail = detailFrom(payload, response.statusText || 'Request failed')
    throw new ApiError(detail, {
      status: response.status,
      code,
      detail,
      fields:
        code === 'validation' && payload && typeof payload === 'object'
          ? /** @type {Record<string, unknown>} */ (payload)
          : undefined,
      retryable: response.status === 429 || response.status >= 500,
    })
  }

  return payload
}

export const api = {
  /**
   * @param {string} path
   * @param {RequestOptions} [options]
   */
  get: (path, options) => request(path, 'GET', options),
  /**
   * @param {string} path
   * @param {RequestOptions} [options]
   */
  post: (path, options) => request(path, 'POST', options),
  /**
   * @param {string} path
   * @param {RequestOptions} [options]
   */
  patch: (path, options) => request(path, 'PATCH', options),
  /**
   * @param {string} path
   * @param {RequestOptions} [options]
   */
  put: (path, options) => request(path, 'PUT', options),
  /**
   * @param {string} path
   * @param {RequestOptions} [options]
   */
  delete: (path, options) => request(path, 'DELETE', options),
}
