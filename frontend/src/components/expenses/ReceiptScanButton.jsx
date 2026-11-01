/** Upload a receipt, extract its total and hand the result to the form. */

import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { prepareUpload } from '../../utils/attachments'
import { useOnlineStatus } from '../../hooks/useOnlineStatus'
import { repository } from '../../services/repository'
import { Button } from '../ui/Button'
import { Alert, AlertDescription } from '../ui/Feedback'

/**
 * @param {{
 *   groupId: string,
 *   expenseId?: string|null,
 *   features: any,
 *   onUploaded?: (attachment: any) => void,
 *   onExtracted: (result: any) => void,
 * }} props
 */
export function ReceiptScanButton({
  groupId,
  expenseId = null,
  features,
  onUploaded,
  onExtracted,
}) {
  const { t } = useTranslation()
  const online = useOnlineStatus()
  const input = useRef(/** @type {HTMLInputElement|null} */ (null))
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  if (!features?.receipt_ai) return null

  /** @param {React.ChangeEvent<HTMLInputElement>} event */
  async function handleFile(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setPending(true)
    setError('')
    setNotice('')
    try {
      const prepared = await prepareUpload(file)
      const attachment = await repository.attachments.upload(groupId, prepared.file, {
        expense_id: expenseId || undefined,
        width: prepared.width,
        height: prepared.height,
      })
      onUploaded?.(attachment)
      // Online scans return the line items immediately so the form can show
      // them before the expense is saved. Offline scans keep the cheaper
      // total-only queue that the sync engine can replay after reconnecting.
      const result = online
        ? await repository.attachments.extractItems(groupId, attachment.id, {
            expense_id: expenseId || undefined,
          })
        : await repository.attachments.extractTotal(groupId, attachment.id)
      if (result.pending) {
        setNotice(
          t(
            'CreateFromReceipt.queued',
            'Queued. The receipt will be scanned after you reconnect.',
          ),
        )
      } else if (
        result.status === 'FAILED' ||
        result.attachment?.receipt_status === 'FAILED'
      ) {
        // A provider failure is a normal 200/FAILED response. Surface the
        // server's reason instead of pretending nothing happened.
        setError(
          (typeof result.error === 'string' && result.error) ||
            t(
              'CreateFromReceipt.scanFailed',
              'The AI could not read this receipt. Check the server AI configuration and try again.',
            ),
        )
      } else {
        onExtracted({ ...result, attachment })
      }
    } catch (caught) {
      setError(
        caught && typeof caught === 'object' && 'detail' in caught
          ? String(caught.detail)
          : t('CreateFromReceipt.ErrorToast.title', 'Error while uploading receipt'),
      )
    } finally {
      setPending(false)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <input
        ref={input}
        type="file"
        accept="image/*"
        hidden
        onChange={handleFile}
      />
      <Button
        variant="outline"
        size="sm"
        disabled={pending}
        onClick={() => input.current?.click()}
      >
        {pending
          ? t('CreateFromReceipt.scanning', 'Scanning…')
          : t('CreateFromReceipt.Dialog.triggerTitle', 'Create expense from receipt')}
      </Button>
      {notice ? (
        <p role="status" className="text-xs text-muted-foreground">
          {notice}
        </p>
      ) : null}
      {!online && !notice ? (
        <p className="text-xs text-muted-foreground">
          {t('CreateFromReceipt.offline', 'Scanning resumes when you are online.')}
        </p>
      ) : null}
      {error ? (
        <Alert variant="destructive" className="py-2">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
