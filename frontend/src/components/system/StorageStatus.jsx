/** Durable storage, quota and backup controls for the group list. */

import { useTranslation } from 'react-i18next'

import { useStorageStatus } from '../../hooks/useStorageStatus'
import { formatBytes } from '../../services/storage'
import { Button } from '../ui/Button'
import { BackupControls } from './BackupControls'

export function StorageStatus() {
  const { t, i18n } = useTranslation()
  const { loading, supported, persisted, usage, quota, level, error, requestPersistence, refresh } =
    useStorageStatus()
  const locale = i18n.resolvedLanguage || 'en-US'
  const ratio = usage != null && quota ? Math.min(100, Math.round((usage / quota) * 100)) : null

  return (
    <section
      data-testid="storage-status"
      className="rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col gap-1">
          <p className="text-sm font-medium text-foreground">
            {t('Storage.title', 'Offline storage')}
          </p>
          {loading && !supported ? (
            <p>{t('Storage.loading', 'Checking this device…')}</p>
          ) : !supported ? (
            <p>{t('Storage.unsupported', 'This browser cannot report storage status.')}</p>
          ) : (
            <p data-testid="storage-usage">
              {t('Storage.usage', '{{used}} of {{quota}} used', {
                used: formatBytes(usage, locale),
                quota: quota ? formatBytes(quota, locale) : t('Storage.unknown', 'unknown'),
              })}
              {ratio != null ? ` · ${ratio}%` : ''}
            </p>
          )}
          <p>
            {persisted
              ? t('Storage.persisted', 'Storage is persistent on this device.')
              : t(
                  'Storage.notPersisted',
                  'The browser may evict offline data if the device runs low on space.',
                )}
          </p>
          {error ? <p role="alert">{error}</p> : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {supported && !persisted ? (
            <Button size="sm" variant="outline" onClick={() => void requestPersistence()}>
              {t('Storage.keep', 'Keep data on this device')}
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => void refresh()}>
            {t('Storage.refresh', 'Refresh')}
          </Button>
        </div>
      </div>

      {level === 'critical' ? (
        <p
          role="alert"
          data-testid="storage-critical"
          className="mt-2 rounded border border-destructive/40 p-2 text-destructive"
        >
          {t(
            'Storage.critical',
            'Storage is almost full. Export a backup now, then remove unused groups.',
          )}
        </p>
      ) : level === 'warning' ? (
        <p
          role="status"
          data-testid="storage-warning"
          className="mt-2 rounded border border-amber-500/40 p-2 text-amber-700 dark:text-amber-400"
        >
          {t('Storage.warning', 'Storage is getting full. A backup is recommended.')}
        </p>
      ) : null}

      <div className="mt-3">
        <BackupControls />
      </div>
    </section>
  )
}
