/** Runtime sync status and conflict queue for the status UI. */

import { useCallback, useEffect, useState } from 'react'

import {
  initialSyncStatus,
  subscribeSyncStatus,
  sync,
  syncNow,
} from '../services/repository'

export function useSyncStatus() {
  const [status, setStatus] = useState(initialSyncStatus)
  const [conflicts, setConflicts] = useState(/** @type {any[]} */ ([]))
  const [loadingConflicts, setLoadingConflicts] = useState(false)

  useEffect(() => subscribeSyncStatus(setStatus), [])

  const refreshConflicts = useCallback(async () => {
    setLoadingConflicts(true)
    try {
      setConflicts(await sync.conflicts())
    } finally {
      setLoadingConflicts(false)
    }
  }, [])

  useEffect(() => {
    if (status.conflicts > 0) void refreshConflicts()
    else setConflicts([])
  }, [status.conflicts, refreshConflicts])

  const resolve = useCallback(
    async (/** @type {number} */ conflictId, /** @type {'mine'|'server'|'duplicate'} */ strategy) => {
      await sync.resolveConflict(conflictId, strategy)
      await refreshConflicts()
    },
    [refreshConflicts],
  )

  return {
    status,
    conflicts,
    loadingConflicts,
    refreshConflicts,
    resolve,
    syncNow: () => syncNow({ reason: 'manual', force: true }),
    retryFailed: () => sync.retryFailed(),
    discardFailed: () => sync.discardFailed(),
  }
}
