/** Full-screen image preview / PDF open dialog. */

import { useTranslation } from 'react-i18next'

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/Dialog'
import { isPdf } from '../../utils/attachments'

/**
 * @param {{
 *   attachment: any|null,
 *   open: boolean,
 *   onOpenChange: (open: boolean) => void,
 * }} props
 */
export function AttachmentPreviewDialog({ attachment, open, onOpenChange }) {
  const { t } = useTranslation()
  const pdf = isPdf(attachment)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>{attachment?.filename || t('Attachments.preview', 'Preview')}</DialogTitle>
        </DialogHeader>
        {attachment && pdf ? (
          <div className="flex flex-col gap-3 py-4 text-sm">
            <p className="text-muted-foreground">
              {t(
                'Attachments.pdfPreviewUnavailable',
                'PDF previews open in a separate tab.',
              )}
            </p>
            <a
              href={attachment.url}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline"
            >
              {t('Attachments.openInNewTab', 'Open in a new tab')}
            </a>
          </div>
        ) : attachment ? (
          <div className="flex max-h-[75vh] items-center justify-center overflow-auto py-4">
            <img
              src={attachment.thumbnail_url || attachment.url}
              alt={attachment.filename || ''}
              className="max-h-[72vh] max-w-full object-contain"
            />
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
