/** Group details and the shared expenses-loaded participant list. */

import { useCallback, useEffect, useState } from 'react'

import { repository } from '../services/repository'

/**
 * @param {string|undefined} groupId
 * @returns {{
 *   group: any|null,
 *   details: any|null,
 *   loading: boolean,
 *   error: any,
 *   reload: () => Promise<void>,
 * }}
 */
export function useGroup(groupId) {
  const [group, setGroup] = useState(/** @type {any|null} */ (null))
  const [details, setDetails] = useState(/** @type {any|null} */ (null))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(/** @type {any} */ (null))
  const [nonce, setNonce] = useState(0)

  const reload = useCallback(async () => setNonce((value) => value + 1), [])

  useEffect(() => {
    if (!groupId) return undefined
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    Promise.all([
      repository.groups.get(groupId, { signal: controller.signal }),
      repository.groups.details(groupId, { signal: controller.signal }),
    ])
      .then(([nextGroup, nextDetails]) => {
        setGroup(nextGroup)
        setDetails(nextDetails)
      })
      .catch((caught) => {
        if (caught && typeof caught === 'object' && caught.code === 'aborted') return
        setError(caught)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [groupId, nonce])

  return { group, details, loading, error, reload }
}
