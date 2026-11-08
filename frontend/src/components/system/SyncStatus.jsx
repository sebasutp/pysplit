/** Global synchronization banner and explicit conflict resolution dialog. */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useSyncStatus } from '../../hooks/useSyncStatus'
import { Button } from '../ui/Button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/Dialog'

export function SyncStatus() {
  const { t } = useTranslation()
  const { status, conflicts, resolve, syncNow, retryFailed, discardFailed } = useSyncStatus()
  const [dialogOpen, setDialogOpen] = useState(false)

  const pending = status.pending > 0
  const failed = status.failed > 0
  const visible =
    !status.online ||
    status.phase === 'syncing' ||
    status.phase === 'error' ||
    status.conflicts > 0 ||
    pending ||
    failed

  if (!visible && !dialogOpen) return null

  return (
    <>
      <div
        role="status"
        data-testid="sync-status"
        className="border-b border-border bg-muted/60 px-4 py-2 text-sm"
      >
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-2">
          <span>
            {!status.online && pending
              ? t('SyncStatus.offlinePending', 'Offline — pending changes: {{count}}', {
                  count: status.pending,
                })
              : !status.online
                ? t('SyncStatus.offlineSaved', 'Offline — showing saved data')
                : status.phase === 'syncing'
                  ? t('SyncStatus.syncing', 'Syncing…')
                  : status.phase === 'error'
                    ? t('SyncStatus.error', 'Sync error: {{error}}', {
                        error: status.lastError || t('SyncStatus.retryToContinue', 'retry to continue'),
                      })
                    : status.conflicts > 0
                      ? t('SyncStatus.conflicts', 'Conflicts needing review: {{count}}', {
                          count: status.conflicts,
                        })
                      : failed
                        ? t('SyncStatus.failed', 'Changes that could not be synced: {{count}}', {
                            count: status.failed,
                          })
                        : t('SyncStatus.pending', 'Pending changes: {{count}}', {
                            count: status.pending,
                          })}
          </span>
          <span className="flex items-center gap-2">
            {failed ? (
              <>
                <Button size="sm" variant="outline" onClick={() => void retryFailed()}>
                  {t('SyncStatus.retryFailed', 'Retry failed changes')}
                </Button>
                <Button size="sm" variant="outline" onClick={() => void discardFailed()}>
                  {t('SyncStatus.discardFailed', 'Discard failed changes')}
                </Button>
              </>
            ) : null}
            {status.phase === 'conflict' || status.conflicts > 0 ? (
              <Button size="sm" variant="outline" onClick={() => setDialogOpen(true)}>
                {t('SyncStatus.resolveConflicts', 'Resolve conflicts')}
              </Button>
            ) : null}
            {status.online ? (
              <Button size="sm" variant="outline" onClick={() => void syncNow()}>
                {t('SyncStatus.syncNow', 'Sync now')}
              </Button>
            ) : null}
          </span>
        </div>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('SyncStatus.dialogTitle', 'Resolve conflicts')}</DialogTitle>
            <DialogDescription>
              {t(
                'SyncStatus.dialogDescription',
                'These edits changed the same records on another device. Choose what to keep.',
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 flex flex-col gap-3">
            {conflicts.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {t('SyncStatus.noConflicts', 'No conflicts to resolve.')}
              </p>
            ) : (
              conflicts.map((conflict) => (
                <div
                  key={conflict.id}
                  data-testid="conflict-row"
                  className="rounded-md border border-border p-3"
                >
                  <p className="text-sm font-medium">
                    {conflict.entity_type} {conflict.entity_id}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t(
                      'SyncStatus.serverVersion',
                      'Server version {{version}} · local edit kept in the conflict queue',
                      { version: conflict.server_version ?? t('Common.unknown', 'unknown') },
                    )}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      onClick={() => void resolve(conflict.id, 'mine')}
                    >
                      {t('SyncStatus.keepMine', 'Keep mine')}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void resolve(conflict.id, 'server')}
                    >
                      {t('SyncStatus.useServer', 'Use server')}
                    </Button>
                    {conflict.entity_type === 'expense' ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void resolve(conflict.id, 'duplicate')}
                      >
                        {t('SyncStatus.duplicate', 'Duplicate as new')}
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
