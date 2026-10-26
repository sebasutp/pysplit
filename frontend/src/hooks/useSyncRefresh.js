import { useEffect } from 'react'

/**
 * Re-run a hook when the sync engine dispatches a local refresh.
 *
 * @param {(updater: (value: number) => number) => void} update
 */
export function useSyncRefresh(update) {
  useEffect(() => {
    const refresh = () => update((value) => value + 1)
    window.addEventListener('pysplit:refresh', refresh)
    return () => window.removeEventListener('pysplit:refresh', refresh)
  }, [update])
}
