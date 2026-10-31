/** Global synchronization banner and explicit conflict resolution dialog. */

import { useState } from 'react'

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
              ? `Offline — ${status.pending} change${status.pending === 1 ? '' : 's'} pending`
              : !status.online
                ? 'Offline — showing saved data'
                : status.phase === 'syncing'
                  ? 'Syncing…'
                  : status.phase === 'error'
                    ? `Sync error: ${status.lastError || 'retry to continue'}`
                    : status.conflicts > 0
                      ? `${status.conflicts} conflict${status.conflicts === 1 ? '' : 's'} need review`
                      : failed
                        ? `${status.failed} change${status.failed === 1 ? '' : 's'} could not be synced`
                        : `${status.pending} change${status.pending === 1 ? '' : 's'} pending`}
          </span>
          <span className="flex items-center gap-2">
            {failed ? (
              <>
                <Button size="sm" variant="outline" onClick={() => void retryFailed()}>
                  Retry failed
                </Button>
                <Button size="sm" variant="outline" onClick={() => void discardFailed()}>
                  Discard failed
                </Button>
              </>
            ) : null}
            {status.phase === 'conflict' || status.conflicts > 0 ? (
              <Button size="sm" variant="outline" onClick={() => setDialogOpen(true)}>
                Resolve conflicts
              </Button>
            ) : null}
            {status.online ? (
              <Button size="sm" variant="outline" onClick={() => void syncNow()}>
                Sync now
              </Button>
            ) : null}
          </span>
        </div>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Resolve conflicts</DialogTitle>
            <DialogDescription>
              These edits changed the same records on another device. Choose what to keep.
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 flex flex-col gap-3">
            {conflicts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No conflicts to resolve.</p>
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
                    Server version {conflict.server_version ?? 'unknown'} · local edit kept in the
                    conflict queue
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      onClick={() => void resolve(conflict.id, 'mine')}
                    >
                      Keep mine
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void resolve(conflict.id, 'server')}
                    >
                      Use server
                    </Button>
                    {conflict.entity_type === 'expense' ? (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void resolve(conflict.id, 'duplicate')}
                      >
                        Duplicate as new
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
