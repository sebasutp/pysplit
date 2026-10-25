/**
 * Analytics path normalisation.
 *
 * Group and expense IDs are capability secrets, so they must never leave the
 * browser in a page-view event.
 */

/**
 * @param {string} path
 * @returns {string}
 */
export function anonymizePath(path) {
  if (typeof path !== 'string') return ''
  const clean = path.split('?')[0].split('#')[0]
  return clean
    .replace(/\/groups\/[^/]+/g, '/groups/[groupId]')
    .replace(/\/expenses\/[^/]+/g, '/expenses/[expenseId]')
    .replace(/\/receipts\/[^/]+/g, '/receipts/[receiptId]')
}
