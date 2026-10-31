/** Install prompt and the explicit service-worker update banner. */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { usePwa } from '../../hooks/usePwa'
import { Button } from '../ui/Button'

export function PwaUpdatePrompt() {
  const { t } = useTranslation()
  const {
    canInstall,
    needRefresh,
    offlineReady,
    error,
    applyUpdate,
    promptInstall,
  } = usePwa()
  const [dismissedOffline, setDismissedOffline] = useState(false)
  const [updating, setUpdating] = useState(false)

  if (!needRefresh && !canInstall && !error && (!offlineReady || dismissedOffline)) {
    return null
  }

  async function reload() {
    setUpdating(true)
    const activated = await applyUpdate()
    if (!activated) setUpdating(false)
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
      {error ? (
        <div
          role="alert"
          data-testid="pwa-error"
          className="rounded-md border border-destructive/40 bg-background p-3 text-sm text-destructive shadow-lg"
        >
          {error}
        </div>
      ) : null}

      {needRefresh ? (
        <div
          role="status"
          data-testid="pwa-update"
          className="rounded-md border border-border bg-background p-3 shadow-lg"
        >
          <p className="text-sm font-medium">{t('Pwa.updateTitle', 'Update available')}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {t(
              'Pwa.updateDescription',
              'A new version of pysplit is ready. Pending changes are kept when you reload.',
            )}
          </p>
          <div className="mt-3 flex justify-end">
            <Button size="sm" disabled={updating} onClick={() => void reload()}>
              {updating
                ? t('Pwa.updating', 'Updating…')
                : t('Pwa.reload', 'Reload to update')}
            </Button>
          </div>
        </div>
      ) : null}

      {!needRefresh && offlineReady && !dismissedOffline ? (
        <div
          role="status"
          data-testid="pwa-offline-ready"
          className="rounded-md border border-border bg-background p-3 text-sm shadow-lg"
        >
          <p className="font-medium">{t('Pwa.offlineReady', 'Ready to work offline')}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {t(
              'Pwa.offlineReadyDescription',
              'The application shell is cached. Open a group once while online to keep its data.',
            )}
          </p>
          <div className="mt-2 flex justify-end">
            <Button size="sm" variant="ghost" onClick={() => setDismissedOffline(true)}>
              {t('Pwa.dismiss', 'Dismiss')}
            </Button>
          </div>
        </div>
      ) : null}

      {!needRefresh && canInstall ? (
        <Button
          data-testid="pwa-install"
          variant="outline"
          className="self-end shadow-lg"
          onClick={() => void promptInstall()}
        >
          {t('Pwa.install', 'Install app')}
        </Button>
      ) : null}
    </div>
  )
}
