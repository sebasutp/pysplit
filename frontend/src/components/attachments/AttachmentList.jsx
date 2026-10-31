/** One unified list for expense images and PDFs. */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '../ui/Button'
import { AttachmentPreviewDialog } from './AttachmentPreviewDialog'
import { attachmentLabel, formatBytes, isPdf } from '../../utils/attachments'

/**
 * @param {{
 *   attachments: any[],
 *   onRemove?: (attachmentId: string) => void,
 *   onScan?: (attachment: any) => void,
 *   onReview?: (attachment: any) => void,
 *   canScan?: boolean,
 *   scanningId?: string|null,
 * }} props
 */
export function AttachmentList({
  attachments,
  onRemove,
  onScan,
  onReview,
  canScan = false,
  scanningId = null,
}) {
  const { t } = useTranslation()
  const [preview, setPreview] = useState(/** @type {any|null} */ (null))

  if (!attachments.length) return null

  return (
    <>
      <ul className="flex flex-col gap-2">
        {attachments.map((attachment) => {
          const pending = Boolean(attachment.pending || attachment.pending_upload)
          const local = String(attachment.url || '').startsWith('local-')
          const pdf = isPdf(attachment)
          return (
            <li
              key={attachment.id}
              className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-background p-2"
            >
              {pending || local ? (
                <span
                  aria-hidden="true"
                  className="flex h-14 w-14 items-center justify-center rounded bg-muted text-xs"
                >
                  …
                </span>
              ) : pdf ? (
                <span
                  aria-hidden="true"
                  className="flex h-14 w-14 items-center justify-center rounded bg-muted text-xl"
                >
                  📄
                </span>
              ) : (
                <button
                  type="button"
                  className="h-14 w-14 overflow-hidden rounded border border-border"
                  onClick={() => setPreview(attachment)}
                  aria-label={t('Attachments.previewNamed', 'Preview {{name}}', {
                    name: attachmentLabel(attachment),
                  })}
                >
                  <img
                    src={attachment.thumbnail_url || attachment.url}
                    alt=""
                    className="h-full w-full object-cover"
                  />
                </button>
              )}

              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{attachmentLabel(attachment)}</p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(attachment.byte_size)}
                  {attachment.receipt_status
                    ? ` · ${t('Attachments.receipt', 'Receipt')}`
                    : ''}
                  {pending || local
                    ? ` · ${t('Attachments.pending', 'Pending upload')}`
                    : ''}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-1">
                {!pending && !local ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      pdf ? window.open(attachment.url, '_blank', 'noreferrer') : setPreview(attachment)
                    }
                  >
                    {pdf
                      ? t('Attachments.open', 'Open')
                      : t('Attachments.previewAction', 'Preview')}
                  </Button>
                ) : null}
                {canScan && onScan && !pdf && !pending && !local && !attachment.receipt_status ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={scanningId === attachment.id}
                    onClick={() => onScan(attachment)}
                  >
                    {scanningId === attachment.id
                      ? t('Attachments.scanning', 'Scanning…')
                      : t('Attachments.scanWithAi', 'Scan with AI')}
                  </Button>
                ) : null}
                {attachment.receipt_status && onReview ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onReview(attachment)}
                  >
                    {t('Attachments.assignItems', 'Assign items')}
                  </Button>
                ) : null}
                {onRemove ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-destructive"
                    disabled={scanningId === attachment.id}
                    onClick={() => onRemove(attachment.id)}
                  >
                    {t('ExpenseForm.DeletePopup.label', 'Delete')}
                  </Button>
                ) : null}
              </div>
            </li>
          )
        })}
      </ul>
      <AttachmentPreviewDialog
        attachment={preview}
        open={Boolean(preview)}
        onOpenChange={(open) => !open && setPreview(null)}
      />
    </>
  )
}
