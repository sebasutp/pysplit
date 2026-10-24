import { useEffect, useState } from 'react'

import { api } from '../../services/api'

/** @typedef {'checking'|'ok'|'offline'} HealthState */

/**
 * Tiny API status probe. It exists so the Stage 1 shell exercises the one HTTP
 * client through the Vite proxy; real feature status is added later.
 */
export function HealthIndicator() {
  /** @type {[HealthState, (value: HealthState) => void]} */
  const [state, setState] = useState(/** @type {HealthState} */ ('checking'))

  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false

    api
      .get('/health', { signal: controller.signal })
      .then((payload) => {
        if (cancelled) return
        const status =
          payload && typeof payload === 'object' && 'status' in payload
            ? /** @type {{status?: unknown}} */ (payload).status
            : null
        setState(status === 'ok' ? 'ok' : 'offline')
      })
      .catch(() => {
        if (!cancelled) setState('offline')
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [])

  const label = state === 'ok' ? 'API ok' : state === 'offline' ? 'API offline' : 'Checking API'
  const tone =
    state === 'ok'
      ? 'bg-emerald-100 text-emerald-900'
      : state === 'offline'
        ? 'bg-amber-100 text-amber-900'
        : 'bg-muted text-muted-foreground'

  return (
    <span
      role="status"
      aria-live="polite"
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}
    >
      {label}
    </span>
  )
}
