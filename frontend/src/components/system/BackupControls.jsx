/** Versioned JSON backup and restore controls. */

import { useRef, useState } from 'react'

import { repository } from '../../services/repository'
import { Button } from '../ui/Button'

export function BackupControls() {
  const input = useRef(/** @type {HTMLInputElement | null} */ (null))
  const [message, setMessage] = useState('')

  async function exportBackup() {
    try {
      const json = await repository.sync.backup()
      const blob = new Blob([json], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `pysplit-backup-${new Date().toISOString().slice(0, 10)}.json`
      anchor.click()
      URL.revokeObjectURL(url)
      setMessage('Backup downloaded.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Backup failed.')
    }
  }

  /** @param {any} event */
  async function restoreBackup(event) {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      await repository.sync.restore(await file.text())
      setMessage('Backup restored. Reloading…')
      window.location.reload()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Restore failed.')
    } finally {
      event.target.value = ''
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <Button size="sm" variant="outline" onClick={() => void exportBackup()}>
        Export backup
      </Button>
      <Button size="sm" variant="outline" onClick={() => input.current?.click()}>
        Restore backup
      </Button>
      <input
        ref={input}
        type="file"
        accept="application/json,.json"
        className="hidden"
        aria-label="Restore backup file"
        onChange={(event) => void restoreBackup(event)}
      />
      {message ? <span role="status">{message}</span> : null}
    </div>
  )
}
