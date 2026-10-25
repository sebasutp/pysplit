/** Paginated expense list with search, filters and cancellation. */

import { useCallback, useEffect, useRef, useState } from 'react'

import { repository } from '../services/repository'

/**
 * @param {string|undefined} groupId
 * @param {{q?: string, from?: string|null, to?: string|null, limit?: number}} [options]
 */
export function useExpenses(groupId, options = {}) {
  const { q = '', from = null, to = null, limit = 100 } = options
  const [state, setState] = useState(
    /** @type {{items: any[], total: number, loading: boolean, error: any, hasMore: boolean}} */ ({
      items: [],
      total: 0,
      loading: true,
      error: null,
      hasMore: false,
    }),
  )
  const [loadingMore, setLoadingMore] = useState(false)
  const [nonce, setNonce] = useState(0)

  // Every filter change starts a new generation. Responses from an older
  // generation (including load-more calls) are discarded.
  const generation = useRef(0)
  // The latest committed state, read by loadMore without stale closures.
  const stateRef = useRef(state)
  stateRef.current = state
  const loadingMoreRef = useRef(false)

  const reload = useCallback(() => setNonce((value) => value + 1), [])

  useEffect(() => {
    if (!groupId) return undefined
    const controller = new AbortController()
    const requestGeneration = generation.current + 1
    generation.current = requestGeneration
    loadingMoreRef.current = false
    setLoadingMore(false)
    setState({ items: [], total: 0, loading: true, error: null, hasMore: false })
    repository.expenses
      .list(groupId, { q, from, to, limit, offset: 0 }, { signal: controller.signal })
      .then((payload) => {
        if (controller.signal.aborted || generation.current !== requestGeneration) return
        const items = payload?.items || []
        const total = payload?.total ?? items.length
        setState({
          items,
          total,
          loading: false,
          error: null,
          hasMore: items.length < total,
        })
      })
      .catch((caught) => {
        if (caught && typeof caught === 'object' && caught.code === 'aborted') return
        if (controller.signal.aborted || generation.current !== requestGeneration) return
        setState((previous) => ({ ...previous, loading: false, error: caught }))
      })
    return () => controller.abort()
  }, [groupId, q, from, to, limit, nonce])

  const loadMore = useCallback(async () => {
    const snapshot = stateRef.current
    if (!groupId || !snapshot.hasMore || snapshot.loading || loadingMoreRef.current) return
    loadingMoreRef.current = true
    setLoadingMore(true)
    const requestGeneration = generation.current
    const offset = snapshot.items.length
    try {
      const payload = await repository.expenses.list(groupId, { q, from, to, limit, offset })
      if (generation.current !== requestGeneration) return
      const nextItems = payload?.items || []
      setState((previous) => {
        const seen = new Set(previous.items.map((/** @type {any} */ item) => item.id))
        const appended = nextItems.filter((/** @type {any} */ item) => !seen.has(item.id))
        const items = appended.length ? [...previous.items, ...appended] : previous.items
        const total = payload?.total ?? previous.total
        return {
          ...previous,
          items,
          total,
          hasMore: appended.length > 0 && items.length < total,
        }
      })
    } catch (caught) {
      if (/** @type {any} */ (caught)?.code === 'aborted') return
      if (generation.current !== requestGeneration) return
      setState((previous) => ({ ...previous, error: caught }))
    } finally {
      if (generation.current === requestGeneration) {
        loadingMoreRef.current = false
        setLoadingMore(false)
      }
    }
  }, [groupId, q, from, to, limit])

  return { ...state, loadingMore, reload, loadMore }
}
