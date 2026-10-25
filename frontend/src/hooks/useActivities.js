/** Activity feed with cursor pagination. */

import { useCallback, useEffect, useRef, useState } from 'react'

import { repository } from '../services/repository'

/** @param {string|undefined} groupId */
export function useActivities(groupId) {
  const [items, setItems] = useState(/** @type {any[]} */ ([]))
  const [nextCursor, setNextCursor] = useState(/** @type {string|null} */ (null))
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(/** @type {any} */ (null))
  const loadingMoreRef = useRef(false)
  const generationRef = useRef(0)
  const loadMoreControllerRef = useRef(/** @type {AbortController|null} */ (null))

  useEffect(() => {
    if (!groupId) return undefined
    const requestGeneration = generationRef.current + 1
    generationRef.current = requestGeneration
    const controller = new AbortController()
    setItems([])
    setNextCursor(null)
    setHasMore(false)
    setError(null)
    setLoading(true)
    loadingMoreRef.current = false
    setLoadingMore(false)
    repository.activities
      .list(groupId, { limit: 50 }, { signal: controller.signal })
      .then((payload) => {
        if (controller.signal.aborted || generationRef.current !== requestGeneration) return
        setItems(payload?.items || [])
        setNextCursor(payload?.next_cursor || null)
        setHasMore(Boolean(payload?.has_more))
        setError(null)
      })
      .catch((caught) => {
        if (caught && typeof caught === 'object' && caught.code === 'aborted') return
        if (!controller.signal.aborted && generationRef.current === requestGeneration) {
          setError(caught)
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && generationRef.current === requestGeneration) {
          setLoading(false)
        }
      })
    return () => {
      controller.abort()
      loadMoreControllerRef.current?.abort()
      generationRef.current += 1
    }
  }, [groupId])

  const loadMore = useCallback(async () => {
    if (!groupId || !nextCursor || !hasMore || loadingMoreRef.current) return
    const requestGeneration = generationRef.current
    const controller = new AbortController()
    loadMoreControllerRef.current = controller
    loadingMoreRef.current = true
    setLoadingMore(true)
    try {
      const payload = await repository.activities.list(
        groupId,
        {
          cursor: Number(nextCursor),
          limit: 50,
        },
        { signal: controller.signal },
      )
      if (generationRef.current !== requestGeneration) return
      const nextItems = payload?.items || []
      setItems((previous) => {
        const seen = new Set(previous.map((/** @type {any} */ item) => item.id))
        const appended = nextItems.filter((/** @type {any} */ item) => !seen.has(item.id))
        return appended.length ? [...previous, ...appended] : previous
      })
      setNextCursor(payload?.next_cursor || null)
      setHasMore(Boolean(payload?.has_more))
    } catch (caught) {
      if (/** @type {any} */ (caught)?.code === 'aborted') return
      if (generationRef.current !== requestGeneration) return
      setError(caught)
    } finally {
      // The new-group effect already reset these when the generation changed;
      // never let a stale request clear the new group's loading state.
      if (generationRef.current === requestGeneration) {
        loadingMoreRef.current = false
        setLoadingMore(false)
      }
    }
  }, [groupId, nextCursor, hasMore])

  return { items, loading, loadingMore, error, hasMore, loadMore }
}
