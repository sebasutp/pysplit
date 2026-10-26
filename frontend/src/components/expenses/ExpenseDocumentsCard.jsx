/** Notes, reimbursement flag and document attachments. */

import { useTranslation } from 'react-i18next'

import { Button } from '../ui/Button'
import { Card, CardContent } from '../ui/Card'
import { FormField } from '../ui/Form'
import { Textarea } from '../ui/Input'

/**
 * @param {{
 *   notes: string,
 *   setNotes: (value: string) => void,
 *   isReimbursement: boolean,
 *   setIsReimbursement: (value: boolean) => void,
 *   handleDocuments: (event: React.ChangeEvent<HTMLInputElement>) => void,
 *   pendingFiles: File[],
 *   documents: any[],
 *   removeDocument: (documentId: string) => void,
 * }} props
 */
export function ExpenseDocumentsCard({
  notes,
  setNotes,
  isReimbursement,
  setIsReimbursement,
  handleDocuments,
  pendingFiles,
  documents,
  removeDocument,
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
          <label className="mb-1 block text-sm font-medium">
            {t('ExpenseForm.attachDocuments', 'Attach documents')}
          </label>
          <input type="file" multiple onChange={handleDocuments} />
          {pendingFiles.length ? (
            <ul className="mt-2 flex flex-col gap-1 text-sm text-muted-foreground">
              {pendingFiles.map((file, index) => (
                <li key={`${file.name}-${index}`}>
                  {file.name} · {t('ExpenseDocumentsInput.pending', 'uploads when saved')}
                </li>
              ))}
            </ul>
          ) : null}
          {documents.length ? (
            <ul className="mt-2 flex flex-col gap-1 text-sm">
              {documents.map((document) => (
                <li key={document.id} className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span className="underline">{document.id}</span>
                    {document.pending || document.pending_upload ? (
                      <span
                        data-testid="document-pending"
                        className="text-xs text-muted-foreground"
                      >
                        {t('ExpenseDocumentsInput.queued', 'Pending upload')}
                      </span>
                    ) : (
                      <a href={document.url} target="_blank" rel="noreferrer" className="underline">
                        {t('ExpenseDocumentsInput.open', 'Open')}
                      </a>
                    )}
                  </span>
                  <Button variant="ghost" size="sm" onClick={() => void removeDocument(document.id)}>
                    {t('ExpenseForm.DeletePopup.label', 'Delete')}
                  </Button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}
