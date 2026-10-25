/** Group balances and suggested reimbursements. */

import { useCallback, useEffect, useState } from 'react'

import { repository } from '../services/repository'

/** @param {string|undefined} groupId */
export function useBalances(groupId) {
  const [balances, setBalances] = useState(/** @type {any[]} */ ([]))
  const [reimbursements, setReimbursements] = useState(/** @type {any[]} */ ([]))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(/** @type {any} */ (null))
  const [nonce, setNonce] = useState(0)
  const reload = useCallback(() => setNonce((value) => value + 1), [])

  useEffect(() => {
    if (!groupId) return undefined
    const controller = new AbortController()
    setLoading(true)
    repository.balances
      .list(groupId, { signal: controller.signal })
      .then((payload) => {
        setBalances(payload?.balances || [])
        setReimbursements(payload?.reimbursements || [])
        setError(null)
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

  return { balances, reimbursements, loading, error, reload }
}
