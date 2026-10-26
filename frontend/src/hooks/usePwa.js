/** PWA install prompt, standalone detection and explicit update state. */

import { useCallback, useEffect, useState } from 'react'

import {
  activateUpdate,
  pwaSupported,
  subscribePwa,
} from '../services/pwa'

/** @returns {boolean} */
function detectStandalone() {
  if (typeof window === 'undefined') return false
  return (
    Boolean(/** @type {any} */ (navigator).standalone) ||
    window.matchMedia?.('(display-mode: standalone)').matches ||
    window.matchMedia?.('(display-mode: fullscreen)').matches ||
    window.matchMedia?.('(display-mode: minimal-ui)').matches
  )
}

export function usePwa() {
  const [pwa, setPwa] = useState(
    /** @type {{needRefresh: boolean, offlineReady: boolean, error: string|null}} */ ({
      needRefresh: false,
      offlineReady: false,
      error: null,
    }),
  )
  const [installEvent, setInstallEvent] = useState(
    /** @type {any|null} */ (null),
  )
  const [installed, setInstalled] = useState(detectStandalone)
  const [standalone, setStandalone] = useState(detectStandalone)

  useEffect(
    () =>
      subscribePwa((value) =>
        setPwa({
          needRefresh: value.needRefresh,
          offlineReady: value.offlineReady,
          error: value.error,
        }),
      ),
    [],
  )

  useEffect(() => {
    if (typeof window === 'undefined') return

    /** @param {any} event */
    function onBeforeInstall(event) {
      // Keep the event so the install button can prompt at a useful moment.
      event.preventDefault()
      setInstallEvent(event)
    }
    function onInstalled() {
      setInstalled(true)
      setInstallEvent(null)
    }
    function onDisplayModeChange() {
      setStandalone(detectStandalone())
    }

    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    window.addEventListener('appinstalled', onInstalled)
    const media = window.matchMedia?.('(display-mode: standalone)')
    media?.addEventListener?.('change', onDisplayModeChange)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      window.removeEventListener('appinstalled', onInstalled)
      media?.removeEventListener?.('change', onDisplayModeChange)
    }
  }, [])

  const promptInstall = useCallback(async () => {
    if (!installEvent) return false
    try {
      await installEvent.prompt()
      const choice = await installEvent.userChoice
      setInstallEvent(null)
      return choice?.outcome === 'accepted'
    } catch {
      setInstallEvent(null)
      return false
    }
  }, [installEvent])

  const applyUpdate = useCallback(async () => activateUpdate(), [])

  return {
    ...pwa,
    canInstall: Boolean(installEvent) && !installed && !standalone,
    installed,
    standalone,
    supported: pwaSupported(),
    promptInstall,
    applyUpdate,
  }
}
