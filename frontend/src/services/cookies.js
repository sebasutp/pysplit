/**
 * Minimal browser cookie reader shared by the HTTP client and i18next.
 *
 * Returns null in non-browser environments such as Vitest without a document,
 * so callers never need their own guard.
 */

/**
 * @param {string} name
 * @returns {string | null}
 */
export function readCookie(name) {
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
