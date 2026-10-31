/**
 * Keep Chromium resource-timing entries safe for React's image estimator.
 *
 * React 19 estimates available bandwidth with `performance.getEntriesByType`
 * when it waits for images in a Suspense boundary. Chromium can briefly return
 * an incomplete entry for an aborted/cancelled resource, and React then throws
 * `Cannot read properties of undefined (reading 'startTime')`. Filtering those
 * entries keeps the estimate working without changing rendering behaviour.
 */

let installed = false

export function stabilizeResourceTiming() {
  if (
    installed ||
    typeof performance === 'undefined' ||
    typeof performance.getEntriesByType !== 'function'
  ) {
    return
  }
  installed = true
  const original = performance.getEntriesByType.bind(performance)
  const wrapped = (/** @type {string} */ type) => {
    const entries = original(type)
    if (type !== 'resource' || !Array.isArray(entries)) return entries
    return entries.filter(
      (entry) => entry && Number.isFinite(Number(entry.startTime)),
    )
  }
  try {
    Object.defineProperty(performance, 'getEntriesByType', {
      configurable: true,
      writable: true,
      value: wrapped,
    })
  } catch {
    // Read-only browsers keep the original method; the estimator still works
    // whenever their entries are complete.
  }
}
