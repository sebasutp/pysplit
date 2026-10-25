/**
 * The single HTTP client.
 *
 * Every request in the application goes through this module. Hooks and
 * components must import the repository, not this file (see
 * docs/repository-contract.md). Keeping the transport here means retries,
 * auth headers, refresh rotation, CSRF, error normalisation and cancellation
 * exist in one place.
 */

import { API_BASE_URL } from './config'

/** @typedef {'not_found'|'validation'|'conflict'|'unauthorized'|'forbidden'|'rate_limited'|'network'|'offline_unsupported'|'server'|'aborted'} ErrorCode */

/**
 * @typedef {Object} RequestOptions
 * @property {unknown} [body] JSON-serialisable value, FormData, or string
 * @property {AbortSignal} [signal]
 * @property {Record<string, string>} [headers]
 * @property {boolean} [keepalive]
 * @property {boolean} [retryAuth] Retry once after refreshing (default true)
 * @property {boolean} [auth] Attach the in-memory bearer token (default true)
 * @property {boolean} [csrf] Attach the double-submit CSRF header
 */

/**
 * @typedef {Object} TextResponse
 * @property {string} content
 * @property {string | null} filename
 * @property {string | null} contentType
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

/** @type {string | null} */
let accessToken = null
/** @type {Promise<boolean> | null} */
let refreshInFlight = null
/** @type {Promise<{access_token: string, user: unknown} | null> | null} */
let sessionRefreshInFlight = null

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
 * Read a browser cookie without pulling in a dependency. Returns null in
 * non-browser environments such as Vitest without a document.
 *
 * @param {string} name
 * @returns {string | null}
 */
function readCookie(name) {
  if (typeof document === 'undefined' || !document.cookie) return null
  for (const part of document.cookie.split(';')) {
    const separator = part.indexOf('=')
    if (separator < 0) continue
    if (part.slice(0, separator).trim() === name) {
      return decodeURIComponent(part.slice(separator + 1).trim())
    }
  }
  return null
}

/** @param {string | null} token */
export function setAccessToken(token) {
  accessToken = token || null
}

/** @returns {string | null} */
export function getAccessToken() {
  return accessToken
}

export function clearAccessToken() {
  accessToken = null
}

/**
 * Perform one HTTP call and normalise its result. No auth retry happens here.
 *
 * @param {string} path
 * @param {string} method
 * @param {RequestOptions} [options]
 * @param {'json'|'text'} [parseAs]
 * @returns {Promise<unknown>}
 */
async function send(path, method, options = {}, parseAs = 'json') {
  const {
    body,
    signal,
    headers = {},
    keepalive = false,
    auth = true,
    csrf = false,
  } = options

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

  if (auth && accessToken) {
    requestHeaders.Authorization = `Bearer ${accessToken}`
  }
  if (csrf) {
    const token = readCookie('pysplit_csrf')
    if (token) requestHeaders['X-CSRF-Token'] = token
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

  if (response.status === 204) {
    return parseAs === 'text'
      ? { content: '', filename: null, contentType: null }
      : undefined
  }

  const contentType = response.headers.get('content-type') || ''

  if (parseAs === 'text') {
    const content = await response.text()
    if (!response.ok) {
      throw new ApiError(content || response.statusText, {
        status: response.status,
        code: codeForStatus(response.status),
        detail: content || response.statusText,
        retryable: response.status === 429 || response.status >= 500,
      })
    }
    return {
      content,
      filename: filenameFrom(response.headers.get('content-disposition')),
      contentType: contentType || null,
    }
  }

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

/**
 * @param {string | null} header
 * @returns {string | null}
 */
function filenameFrom(header) {
  if (!header) return null
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (utf8) return decodeURIComponent(utf8[1])
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain ? plain[1] : null
}

/**
 * Rotate the refresh cookie and store the new access token. Returns null when
 * there is no valid session. Shared by boot, explicit refresh and the
 * one-retry path on 401.
 *
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<{access_token: string, user: unknown}|null>}
 */
export async function refreshSession(options = {}) {
  // React StrictMode mounts the auth provider twice in development, and an
  // automatic 401 retry may race the boot refresh. Rotating the same refresh
  // token twice revokes the family, so all callers share one request.
  if (sessionRefreshInFlight) return sessionRefreshInFlight
  sessionRefreshInFlight = (async () => {
    try {
      const payload = await send(
        '/auth/refresh',
        'POST',
        { signal: options.signal, auth: false, csrf: true },
        'json',
      )
      if (
        payload &&
        typeof payload === 'object' &&
        'access_token' in payload &&
        typeof /** @type {{access_token?: unknown}} */ (payload).access_token === 'string'
      ) {
        accessToken = /** @type {{access_token: string}} */ (payload).access_token
        return /** @type {{access_token: string, user: unknown}} */ (payload)
      }
      accessToken = null
      return null
    } catch (error) {
      if (error instanceof ApiError && error.code === 'unauthorized') {
        accessToken = null
        return null
      }
      throw error
    } finally {
      sessionRefreshInFlight = null
    }
  })()
  return sessionRefreshInFlight
}

/**
 * @returns {Promise<boolean>}
 */
async function refreshAccessToken() {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    try {
      const result = await refreshSession()
      return Boolean(result)
    } catch {
      return false
    } finally {
      refreshInFlight = null
    }
  })()
  return refreshInFlight
}

/**
 * Perform an HTTP request and normalise success/failure. A 401 on an
 * authenticated call triggers exactly one refresh attempt.
 *
 * @param {string} path
 * @param {string} method
 * @param {RequestOptions} [options]
 * @param {'json'|'text'} [parseAs]
 * @returns {Promise<unknown>}
 */
async function request(path, method, options = {}, parseAs = 'json') {
  const { retryAuth = true, auth = true } = options
  try {
    return await send(path, method, options, parseAs)
  } catch (error) {
    if (
      retryAuth &&
      auth &&
      error instanceof ApiError &&
      error.code === 'unauthorized' &&
      !path.startsWith('/auth/')
    ) {
      const refreshed = await refreshAccessToken()
      if (refreshed) {
        return await send(path, method, options, parseAs)
      }
    }
    throw error
  }
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
  /**
   * Fetch a text file (exports). Keeps filename/content-type metadata next to
   * the body so callers never need a second HTTP path.
   *
   * @param {string} path
   * @param {RequestOptions} [options]
   * @returns {Promise<TextResponse>}
   */
  text: async (path, options) => {
    const result = await request(path, 'GET', options, 'text')
    return /** @type {TextResponse} */ (result)
  },
  refreshSession,
  getAccessToken,
  setAccessToken,
  clearAccessToken,
}
