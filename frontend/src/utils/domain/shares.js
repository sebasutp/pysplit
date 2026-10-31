/**
 * Expense share apportionment.
 *
 * Pure JavaScript mirror of `backend/app/utils/shares.py`, which in turn
 * mirrors `spliit/src/lib/shares.ts`. Money is integer minor units and shares
 * always add up to exactly the expense amount, including negative amounts.
 */

export const EVENLY = 'EVENLY'

/**
 * FNV-1a over JavaScript UTF-16 code units, returned unsigned.
 *
 * @param {string} value
 * @returns {number}
 */
export function hashString(value) {
  let result = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index)
    result = Math.imul(result, 0x01000193) >>> 0
  }
  return result >>> 0
}

/**
 * Split `amount` over `shares` using largest-remainder apportionment.
 *
 * @param {number} amount
 * @param {number[]} shares
 * @param {number} totalShares
 * @param {number} offset
 * @returns {number[]}
 */
export function apportion(amount, shares, totalShares, offset) {
  const count = shares.length
  if (count === 0) return []
  if (totalShares === 0) return Array.from({ length: count }, () => 0)

  /** @type {number[]} */
  const amounts = []
  /** @type {{index: number, remainder: number}[]} */
  const remainders = []
  let distributed = 0

  for (let index = 0; index < shares.length; index += 1) {
    const exact = amount * shares[index]
    const base = Math.floor(exact / totalShares)
    amounts.push(base)
    distributed += base
    remainders.push({ index, remainder: exact - base * totalShares })
  }

  const remaining = amount - distributed
  if (remaining === 0) return amounts

  /** @param {number} index */
  const rotation = (index) => (index - offset + count) % count
  remainders.sort((first, second) => {
    if (second.remainder !== first.remainder) return second.remainder - first.remainder
    return rotation(first.index) - rotation(second.index)
  })

  const winners = Math.max(0, Math.min(remaining, count))
  for (let position = 0; position < winners; position += 1) {
    amounts[remainders[position].index] += 1
  }
  return amounts
}

/**
 * @param {number} amount
 * @param {number} count
 * @returns {number[]}
 */
export function distributeAmount(amount, count) {
  return apportion(amount, Array.from({ length: count }, () => 1), count, 0)
}

/**
 * @param {number} amount
 * @param {number[]} weights
 * @returns {number[]}
 */
export function weightedApportion(amount, weights) {
  if (!weights.length) return []
  return apportion(
    amount,
    weights,
    weights.reduce((sum, weight) => sum + weight, 0),
    0,
  )
}

/** @typedef {{participant_id: string, shares: number}} ShareRow */

/**
 * @param {any} expense
 * @returns {ShareRow[]}
 */
function paidForRows(expense) {
  const raw = expense?.paid_for ?? expense?.paidFor ?? []
  /** @type {ShareRow[]} */
  const rows = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    let participantId = item.participant_id
    if (participantId == null && item.participant && typeof item.participant === 'object') {
      participantId = item.participant.id
    }
    if (participantId == null) continue
    rows.push({ participant_id: String(participantId), shares: Number(item.shares ?? 1) })
  }
  return rows
}

/**
 * @param {any} expense
 * @returns {Map<string, number>}
 */
export function getExpenseShares(expense) {
  const paidFor = paidForRows(expense).sort((first, second) =>
    first.participant_id < second.participant_id
      ? -1
      : first.participant_id > second.participant_id
        ? 1
        : 0,
  )
  const splitMode = String(expense?.split_mode ?? expense?.splitMode ?? EVENLY)

  const weights =
    splitMode === 'BY_SHARES' || splitMode === 'BY_PERCENTAGE' || splitMode === 'BY_AMOUNT'
      ? paidFor.map((row) => row.shares)
      : Array.from({ length: paidFor.length }, () => 1)
  const totalShares = weights.reduce((sum, weight) => sum + weight, 0)

  const expenseId = expense?.id
  const offset =
    expenseId && paidFor.length
      ? hashString(String(expenseId)) % paidFor.length
      : 0

  const amount = Number(expense?.amount ?? 0)
  const amounts = apportion(amount, weights, totalShares, offset)
  /** @type {Map<string, number>} */
  const result = new Map()
  paidFor.forEach((row, index) => result.set(row.participant_id, amounts[index]))
  return result
}

/**
 * @param {string|null|undefined} participantId
 * @param {any} expense
 * @returns {number}
 */
export function getParticipantShare(participantId, expense) {
  if (participantId == null) return 0
  return getExpenseShares(expense).get(participantId) ?? 0
}
