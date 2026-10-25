/** Activity feed with cursor pagination. */

import { useCallback, useEffect, useState } from 'react'

import { repository } from '../services/repository'

/** @param {string|undefined} groupId */
export function useActivities(groupId) {
  const [items, setItems] = useState(/** @type {any[]} */ ([]))
  const [nextCursor, setNextCursor] = useState(/** @type {string|null} */ (null))
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(/** @type {any} */ (null))

  useEffect(() => {
    if (!groupId) return undefined
    const controller = new AbortController()
    setLoading(true)
    repository.activities
      .list(groupId, { limit: 50 }, { signal: controller.signal })
      .then((payload) => {
        setItems(payload?.items || [])
        setNextCursor(payload?.next_cursor || null)
        setHasMore(Boolean(payload?.has_more))
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
  }, [groupId])

  const loadMore = useCallback(async () => {
    if (!groupId || !nextCursor || !hasMore) return
    const payload = await repository.activities.list(groupId, {
      cursor: Number(nextCursor),
      limit: 50,
    })
    setItems((previous) => [...previous, ...(payload?.items || [])])
    setNextCursor(payload?.next_cursor || null)
    setHasMore(Boolean(payload?.has_more))
  }, [groupId, nextCursor, hasMore])

  return { items, loading, error, hasMore, loadMore }
}
