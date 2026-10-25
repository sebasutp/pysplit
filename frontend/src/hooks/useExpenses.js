/** Paginated expense list with search, filters and cancellation. */

import { useCallback, useEffect, useState } from 'react'

import { repository } from '../services/repository'

/**
 * @param {string|undefined} groupId
 * @param {{q?: string, from?: string|null, to?: string|null, limit?: number}} [options]
 */
export function useExpenses(groupId, options = {}) {
  const { q = '', from = null, to = null, limit = 100 } = options
  const [state, setState] = useState(
    /** @type {{items: any[], total: number, loading: boolean, error: any}} */ ({
      items: [],
      total: 0,
      loading: true,
      error: null,
    }),
  )
  const [nonce, setNonce] = useState(0)

  const reload = useCallback(() => setNonce((value) => value + 1), [])

  useEffect(() => {
    if (!groupId) return undefined
    const controller = new AbortController()
    setState((previous) => ({ ...previous, loading: true, error: null }))
    repository.expenses
      .list(
        groupId,
        { q, from, to, limit, offset: 0 },
        { signal: controller.signal },
      )
      .then((payload) => {
        setState({
          items: payload?.items || [],
          total: payload?.total ?? 0,
          loading: false,
          error: null,
        })
      })
      .catch((caught) => {
        if (caught && typeof caught === 'object' && caught.code === 'aborted') return
        setState((previous) => ({ ...previous, loading: false, error: caught }))
      })
    return () => controller.abort()
  }, [groupId, q, from, to, limit, nonce])

  return { ...state, reload }
}
