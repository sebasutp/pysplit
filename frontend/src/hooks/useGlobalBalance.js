/**
 * Cross-group balance aggregation.
 *
 * The reference stores the active participant per group in localStorage, so
 * the card only appears after the user has identified themselves somewhere.
 */

import { useEffect, useState } from 'react'

import { repository } from '../services/repository'
import { getActiveUser } from '../utils/recent-groups'

/**
 * @typedef {{group_id: string, participant_id: string}} ActiveUserEntry
 * @typedef {{group_id: string, group_name: string, currency: string,
 *   currency_code?: string|null, participant_id: string,
 *   participant_name: string, amount: number}} UserBalance
 */

/**
 * @param {{id: string, name: string}[]} groups
 */
export function useGlobalBalance(groups) {
  const [entries, setEntries] = useState(/** @type {ActiveUserEntry[] | null} */ (null))
  const [balances, setBalances] = useState(/** @type {UserBalance[]} */ ([]))
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    /** @type {ActiveUserEntry[]} */
    const next = []
    for (const group of groups) {
      const participantId = getActiveUser(group.id)
      if (participantId) next.push({ group_id: group.id, participant_id: participantId })
    }
    setEntries(next)
  }, [groups])

  useEffect(() => {
    if (!entries || entries.length === 0) {
      setBalances([])
      setLoading(false)
      return undefined
    }
    const controller = new AbortController()
    setLoading(true)
    repository.balances
      .forUser(entries, { signal: controller.signal })
      .then((items) => setBalances(items))
      .catch((error) => {
        if (error && typeof error === 'object' && 'code' in error && error.code === 'aborted') {
          return
        }
        setBalances([])
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [entries])

  return { entries, balances, loading }
}
