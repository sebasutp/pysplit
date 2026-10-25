/**
 * Pure expense calculations used by cards, forms and the active-user display.
 *
 * These mirror app/utils/shares.py. The server remains authoritative; the
 * helpers only format what the API already returned.
 */

/** @typedef {{id: string, name: string}} Participant */
/** @typedef {{participant_id: string, shares: number}} PaidFor */
/** @typedef {{
 *   amount: number,
 *   paid_by_id: string,
 *   split_mode: string,
 *   paid_for: PaidFor[]
 * }} ExpenseLike */

/**
 * Amount owed by one participant for an expense, in minor units.
 *
 * @param {ExpenseLike} expense
 * @param {string} participantId
 * @returns {number}
 */
export function shareForParticipant(expense, participantId) {
  const rows = expense.paid_for || []
  const row = rows.find((item) => item.participant_id === participantId)
  if (!row) return 0
  const amount = expense.amount
  if (expense.split_mode === 'BY_AMOUNT') return row.shares
  if (expense.split_mode === 'BY_SHARES') {
    const total = rows.reduce((sum, item) => sum + item.shares, 0)
    if (!total) return 0
    return Math.round((amount * row.shares) / total)
  }
  if (expense.split_mode === 'BY_PERCENTAGE') {
    return Math.round((amount * row.shares) / 10_000)
  }
  if (!rows.length) return 0
  return Math.round(amount / rows.length)
}

/**
 * The active user's net balance on a single expense.
 *
 * @param {ExpenseLike} expense
 * @param {string|null|undefined} participantId
 * @returns {number|null} null when the participant is not involved
 */
export function balanceForParticipant(expense, participantId) {
  if (!participantId) return null
  const involved =
    expense.paid_by_id === participantId ||
    (expense.paid_for || []).some((row) => row.participant_id === participantId)
  if (!involved) return 0
  const paid = expense.paid_by_id === participantId ? expense.amount : 0
  return paid - shareForParticipant(expense, participantId)
}

/**
 * @param {PaidFor[]|undefined} paidFor
 * @param {Participant[]} participants
 * @returns {string[]}
 */
export function participantNames(paidFor, participants) {
  const included = new Set((paidFor || []).map((row) => row.participant_id))
  const ordered = participants
    .filter((participant) => included.has(participant.id))
    .map((participant) => participant.name)
  const known = new Set(participants.map((participant) => participant.id))
  for (const row of paidFor || []) {
    if (!known.has(row.participant_id)) ordered.push(row.participant_id)
  }
  return ordered
}

/**
 * @param {PaidFor[]|undefined} paidFor
 * @param {Participant[]} participants
 * @returns {string}
 */
export function paidForLabel(paidFor, participants) {
  const names = participantNames(paidFor, participants)
  if (!names.length) return ''
  if (names.length === participants.length) return 'everyone'
  return names.join(', ')
}

/** @type {Record<string, string>} */
const CATEGORY_ICONS = {
  Entertainment: '🎬',
  'Food and Drink': '🍽',
  Home: '🏠',
  Life: '🌱',
  Transportation: '🚗',
  Utilities: '💡',
  Uncategorized: '🏷',
}

/**
 * A small category icon for list rows, keyed by the reference grouping.
 *
 * @param {{grouping?: string, name?: string}|null|undefined} category
 * @returns {string}
 */
export function categoryIcon(category) {
  if (!category || !category.grouping) return '🏷'
  return CATEGORY_ICONS[category.grouping] || '🏷'
}

/**
 * Whether an expense is an income (negative amount).
 *
 * @param {number} amount
 * @returns {boolean}
 */
export function isIncome(amount) {
  return amount < 0
}
