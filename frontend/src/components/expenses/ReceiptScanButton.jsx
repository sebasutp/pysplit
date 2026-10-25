/** Optional "create expense from receipt" upload used by the expense form. */

import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { compressImage, imageDimensions } from '../../utils/compress-image'
import { repository } from '../../services/repository'
import { Button } from '../ui/Button'
import { Alert, AlertDescription } from '../ui/Feedback'

/**
 * @param {{
 *   groupId: string,
 *   features: any,
 *   onExtracted: (result: any) => void,
 * }} props
 */
export function ReceiptScanButton({ groupId, features, onExtracted }) {
  const { t } = useTranslation()
  const input = useRef(/** @type {HTMLInputElement|null} */ (null))
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  if (!features?.receipt_extract) return null

  /** @param {React.ChangeEvent<HTMLInputElement>} event */
  async function handleFile(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setPending(true)
    setError('')
    try {
      const compressed = await compressImage(file)
      const size = await imageDimensions(compressed)
      const image = await repository.receipts.upload(groupId, compressed, size)
      const result = await repository.receipts.extractTotal(groupId, {
        image_url: image.url,
      })
      onExtracted(result)
    } catch (caught) {
      setError(
        caught && typeof caught === 'object' && 'detail' in caught
          ? String(caught.detail)
          : t('CreateFromReceipt.ErrorToast.title', 'Error while uploading document'),
      )
    } finally {
      setPending(false)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <input ref={input} type="file" accept="image/*" hidden onChange={handleFile} />
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
      {error ? (
        <Alert variant="destructive" className="py-2">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
