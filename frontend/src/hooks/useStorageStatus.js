/** Storage persistence and quota state for the settings panel. */

import { useCallback, useEffect, useState } from 'react'

import { readStorageStatus } from '../services/storage'

/** @type {{loading: boolean, supported: boolean, persisted: boolean|null, usage: number|null, quota: number|null, level: 'unknown'|'ok'|'warning'|'critical', error: string|null}} */
const INITIAL = {
  loading: true,
  supported: false,
  persisted: null,
  usage: null,
  quota: null,
  level: 'unknown',
  error: null,
}

export function useStorageStatus() {
  const [state, setState] = useState(INITIAL)

  const refresh = useCallback(async (/** @type {{persist?: boolean}} */ options = {}) => {
    setState((previous) => ({ ...previous, loading: true }))
    const next = await readStorageStatus(options)
    setState({ loading: false, ...next })
    return next
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const requestPersistence = useCallback(async () => {
    return refresh({ persist: true })
  }, [refresh])

  return { ...state, refresh, requestPersistence }
}
