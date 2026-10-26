/** Group details and the shared expenses-loaded participant list. */

import { useCallback, useEffect, useState } from 'react'

import { repository } from '../services/repository'
import { useSyncRefresh } from './useSyncRefresh'

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
  const [state, setState] = useState(
    /** @type {{id: string|null, group: any|null, details: any|null, loading: boolean, error: any}} */ ({
      id: null,
      group: null,
      details: null,
      loading: true,
      error: null,
    }),
  )
  const [nonce, setNonce] = useState(0)

  const reload = useCallback(async () => setNonce((value) => value + 1), [])

  useSyncRefresh(setNonce)

  useEffect(() => {
    if (!groupId) {
      setState({ id: null, group: null, details: null, loading: false, error: null })
      return undefined
    }
    const controller = new AbortController()
    // A reload of the same group keeps the current data visible; only a new id
    // discards it.
    setState((previous) =>
      previous.id === groupId
        ? { ...previous, loading: true, error: null }
        : { id: groupId, group: null, details: null, loading: true, error: null },
    )
    Promise.all([
      repository.groups.get(groupId, { signal: controller.signal }),
      repository.groups.details(groupId, { signal: controller.signal }),
    ])
      .then(([nextGroup, nextDetails]) => {
        if (controller.signal.aborted) return
        setState({
          id: groupId,
          group: nextGroup,
          details: nextDetails,
          loading: false,
          error: null,
        })
      })
      .catch((caught) => {
        if (caught && typeof caught === 'object' && caught.code === 'aborted') return
        if (controller.signal.aborted) return
        setState((previous) =>
          previous.id === groupId ? { ...previous, loading: false, error: caught } : previous,
        )
      })
    return () => controller.abort()
  }, [groupId, nonce])

  // Until the effect for a new id has committed, expose a neutral state rather
  // than the group that was loaded for the previous id.
  const current = state.id === groupId
  return {
    group: current ? state.group : null,
    details: current ? state.details : null,
    loading: current ? state.loading : Boolean(groupId),
    error: current ? state.error : null,
    reload,
  }
}
