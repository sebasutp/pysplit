/** Notes, reimbursement flag and unified attachments. */

import { useTranslation } from 'react-i18next'

import { AttachmentList } from '../attachments/AttachmentList'
import { ReceiptItemsPreview } from '../attachments/ReceiptItemsPreview'
import { Card, CardContent } from '../ui/Card'
import { FormField } from '../ui/Form'
import { Textarea } from '../ui/Input'

/**
 * @param {{
 *   notes: string,
 *   setNotes: (value: string) => void,
 *   isReimbursement: boolean,
 *   setIsReimbursement: (value: boolean) => void,
 *   handleAttachments: (event: React.ChangeEvent<HTMLInputElement>) => void,
 *   attachments: any[],
 *   removeAttachment: (attachmentId: string) => void,
 *   onScan?: (attachment: any) => void,
 *   onReview?: (attachment: any) => void,
 *   canScan?: boolean,
 *   scanningId?: string|null,
 *   receipt?: any|null,
 *   currency?: any,
 *   locale?: string,
 * }} props
 */
export function ExpenseDocumentsCard({
  notes,
  setNotes,
  isReimbursement,
  setIsReimbursement,
  handleAttachments,
  attachments,
  removeAttachment,
  onScan,
  onReview,
  canScan = false,
  scanningId = null,
  receipt = null,
  currency = null,
  locale = 'en-US',
}) {
  const { t } = useTranslation()

  return (
    <Card>
      <CardContent className="grid gap-4 pt-5">
        <FormField label={t('ExpenseForm.notesField.label', 'Notes')} htmlFor="expense-notes">
          <Textarea
            id="expense-notes"
            name="notes"
            rows={2}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
          />
        </FormField>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            name="isReimbursement"
            checked={isReimbursement}
            onChange={(event) => setIsReimbursement(event.target.checked)}
          />
          {t('ExpenseForm.isReimbursementField.label', 'This is a reimbursement')}
        </label>
        <div>
          <label className="mb-1 block text-sm font-medium" htmlFor="expense-attachments">
            {t('ExpenseForm.attachDocuments', 'Attach documents')}
          </label>
          <input
            id="expense-attachments"
            type="file"
            multiple
            accept="image/*,application/pdf"
            onChange={handleAttachments}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            {t(
              'Attachments.help',
              'Images are compressed before upload. PDFs are kept as attachments and open in a new tab.',
            )}
          </p>
          <div className="mt-2">
            <AttachmentList
              attachments={attachments}
              onRemove={removeAttachment}
              onScan={onScan}
              onReview={onReview}
              canScan={canScan}
              scanningId={scanningId}
            />
            <ReceiptItemsPreview receipt={receipt} currency={currency} locale={locale} />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
