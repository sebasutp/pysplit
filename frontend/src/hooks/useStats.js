/** Statistics overview and drill-downs. */

import { useCallback, useEffect, useState } from 'react'

import { repository } from '../services/repository'
import { useSyncRefresh } from './useSyncRefresh'

/**
 * @param {string|undefined} groupId
 * @param {{participantId?: string|null, from?: string|null, to?: string|null}} [options]
 */
export function useStats(groupId, options = {}) {
  const { participantId = null, from = null, to = null } = options
  const [stats, setStats] = useState(/** @type {any|null} */ (null))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(/** @type {any} */ (null))
  const [nonce, setNonce] = useState(0)
  const reload = useCallback(() => setNonce((value) => value + 1), [])

  useSyncRefresh(setNonce)

  useEffect(() => {
    if (!groupId) return undefined
    const controller = new AbortController()
    setLoading(true)
    repository.stats
      .overview(
        groupId,
        { participant_id: participantId, from, to },
        { signal: controller.signal },
      )
      .then((payload) => {
        setStats(payload)
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
  }, [groupId, participantId, from, to, nonce])

  return { stats, loading, error, reload }
}

/**
 * @param {string} groupId
 * @param {{kind: 'category', categoryId: number}|{kind: 'month', month: string}|null} target
 * @param {{from?: string|null, to?: string|null}} [range]
 */
export function useDrilldown(groupId, target, range = {}) {
  const [expenses, setExpenses] = useState(/** @type {any[]} */ ([]))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(/** @type {any} */ (null))
  const targetKind = target?.kind ?? null
  const targetKey =
    target?.kind === 'category'
      ? target.categoryId
      : target?.kind === 'month'
        ? target.month
        : null

  useEffect(() => {
    if (!groupId || !target) {
      setExpenses([])
      setLoading(false)
      setError(null)
      return undefined
    }
    const controller = new AbortController()
    // Clear the previous selection before the new request resolves.
    setExpenses([])
    setLoading(true)
    setError(null)
    const request =
      target.kind === 'category'
        ? repository.stats.categoryExpenses(
            groupId,
            target.categoryId,
            { from: range.from, to: range.to },
            { signal: controller.signal },
          )
        : repository.stats.monthExpenses(
            groupId,
            target.month,
            { from: range.from, to: range.to },
            { signal: controller.signal },
          )
    request
      .then((payload) => {
        if (!controller.signal.aborted) setExpenses(payload?.expenses || [])
      })
      .catch((caught) => {
        if (caught && typeof caught === 'object' && caught.code === 'aborted') return
        if (!controller.signal.aborted) setError(caught)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupId, targetKind, targetKey, range.from, range.to])

  return { expenses, loading, error }
}
