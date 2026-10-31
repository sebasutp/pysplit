/**
 * Receipt line-item allocation.
 *
 * Pure JavaScript mirror of `backend/app/utils/receipt_split.py`. Money is
 * integer minor units and quantities are integer thousandths.
 */

import { distributeAmount, weightedApportion } from './shares'

export const PARTICIPANT = 'PARTICIPANT'
export const SHARED = 'SHARED'

/** @typedef {{target: string, participant_id: string|null, quantity_milli: number}} ReceiptPortion */
/** @typedef {{amount: number, quantity_milli: number, portions: ReceiptPortion[]}} ReceiptSplitItem */

/**
 * @param {any} source
 * @param {string[]} keys
 * @param {any} [fallback]
 * @returns {any}
 */
function value(source, keys, fallback = null) {
  if (source && typeof source === 'object') {
    for (const key of keys) {
      if (Object.prototype.hasOwnProperty.call(source, key)) return source[key]
    }
  }
  return fallback
}

/**
 * @param {any} source
 * @returns {ReceiptPortion}
 */
function portion(source) {
  return {
    target: String(value(source, ['target'], PARTICIPANT)),
    participant_id: value(source, ['participant_id', 'participantId']),
    quantity_milli: Number(value(source, ['quantity_milli', 'quantityMilli'], 0)),
  }
}

/**
 * @param {any} source
 * @returns {ReceiptSplitItem}
 */
function splitItem(source) {
  const portions = value(source, ['portions'], []) || []
  return {
    amount: Number(value(source, ['amount'], 0)),
    quantity_milli: Number(value(source, ['quantity_milli', 'quantityMilli'], 1000)),
    portions: Array.isArray(portions) ? portions.map(portion) : [],
  }
}

/**
 * @param {any[]} items
 * @returns {ReceiptSplitItem[]}
 */
export function toReceiptSplitItems(items) {
  return items.map((raw) => {
    const item = splitItem(raw)
    let portions = item.portions
    if (!portions.length && Boolean(value(raw, ['is_shared', 'isShared'], false))) {
      portions = [
        { target: SHARED, participant_id: null, quantity_milli: item.quantity_milli },
      ]
    }
    return { amount: item.amount, quantity_milli: item.quantity_milli, portions }
  })
}

/**
 * `Math.trunc(value) || 0` with tolerant parsing.
 *
 * @param {any} raw
 * @returns {number}
 */
function truncQuantity(raw) {
  const number = Number(raw)
  if (Number.isNaN(number)) return 0
  if (!Number.isFinite(number)) return number
  return Math.trunc(number)
}

/**
 * `Math.floor(value)` with tolerant parsing.
 *
 * @param {any} raw
 * @returns {number}
 */
function consumeQuantity(raw) {
  const number = Number(raw)
  if (Number.isNaN(number)) return 0
  if (!Number.isFinite(number)) return number
  return Math.floor(number)
}

/**
 * @param {any} item
 * @param {Set<string>|string[]} knownParticipantIds
 * @returns {{portions: ReceiptPortion[], remaining: number|null}}
 */
export function consumeItemPortions(item, knownParticipantIds) {
  const split = splitItem(item)
  const known = new Set(knownParticipantIds)
  const total = Math.max(truncQuantity(split.quantity_milli), 1)
  let remaining = total
  const portions = []

  for (const current of split.portions) {
    const quantity = consumeQuantity(current.quantity_milli)
    if (!(quantity > 0)) continue
    if (current.target === PARTICIPANT) {
      const participantId = current.participant_id
      if (!participantId || !known.has(participantId)) continue
      const allowed = Math.min(quantity, remaining)
      if (allowed <= 0) continue
      remaining -= allowed
      portions.push({
        target: PARTICIPANT,
        participant_id: participantId,
        quantity_milli: Math.trunc(allowed) || 0,
      })
    } else {
      const allowed = Math.min(quantity, remaining)
      if (allowed <= 0) continue
      remaining -= allowed
      portions.push({
        target: SHARED,
        participant_id: null,
        quantity_milli: Math.trunc(allowed) || 0,
      })
    }
  }
  return {
    portions,
    remaining: Number.isFinite(remaining) ? Math.trunc(remaining) : null,
  }
}

/**
 * @param {string[]} participantIds
 * @param {string[]} optedOutParticipantIds
 * @param {any[]} items
 * @returns {any}
 */
export function computeReceiptSplit(participantIds, optedOutParticipantIds, items) {
  const participants = [...new Set(participantIds.map(String))]
  const participantSet = new Set(participants)
  const optedOut = new Set(
    optedOutParticipantIds.map(String).filter((participantId) => participantSet.has(participantId)),
  )

  const itemList = items.map(splitItem)
  /** @type {Map<string, number>} */
  const direct = new Map()
  let sharedPool = 0
  let unassignedPool = 0

  for (const item of itemList) {
    const consumed = consumeItemPortions(item, participantSet)
    const unassignedValue = consumed.remaining || 0

    /** @type {{kind: string, participantId: string|null}[]} */
    const destinations = []
    /** @type {number[]} */
    const weights = []
    let sharedWeight = 0

    for (const current of consumed.portions) {
      if (current.target === PARTICIPANT && current.participant_id != null) {
        weights.push(current.quantity_milli)
        destinations.push({ kind: 'direct', participantId: current.participant_id })
      } else {
        sharedWeight += current.quantity_milli
      }
    }
    if (sharedWeight > 0) {
      weights.push(sharedWeight)
      destinations.push({ kind: 'shared', participantId: null })
    }
    if (unassignedValue > 0) {
      weights.push(unassignedValue)
      destinations.push({ kind: 'unassigned', participantId: null })
    }

    const amounts = weightedApportion(item.amount, weights)
    destinations.forEach((destination, index) => {
      if (destination.kind === 'direct' && destination.participantId != null) {
        direct.set(
          destination.participantId,
          (direct.get(destination.participantId) ?? 0) + amounts[index],
        )
      } else if (destination.kind === 'shared') {
        sharedPool += amounts[index]
      } else {
        unassignedPool += amounts[index]
      }
    })
  }

  const sharedShares = distributeAmount(sharedPool, participants.length)
  const sharers = participants.filter((participantId) => !optedOut.has(participantId))
  const unassignedShares = distributeAmount(unassignedPool, sharers.length)
  const sharerIndex = new Map(sharers.map((participantId, index) => [participantId, index]))

  const participantShares = participants.map((participantId, index) => {
    const directAmount = direct.get(participantId) ?? 0
    const sharedAmount = index < sharedShares.length ? sharedShares[index] : 0
    let unassignedAmount = 0
    if (!optedOut.has(participantId)) {
      const position = sharerIndex.get(participantId)
      if (position != null && position < unassignedShares.length) {
        unassignedAmount = unassignedShares[position]
      }
    }
    return {
      participant_id: participantId,
      direct: directAmount,
      shared: sharedAmount,
      unassigned: unassignedAmount,
      total: directAmount + sharedAmount + unassignedAmount,
    }
  })

  return {
    participants: participantShares,
    items_total: itemList.reduce((sum, item) => sum + item.amount, 0),
    shared_pool: sharedPool,
    unassigned_pool: unassignedPool,
    all_opted_out: sharers.length === 0 && unassignedPool !== 0,
  }
}
