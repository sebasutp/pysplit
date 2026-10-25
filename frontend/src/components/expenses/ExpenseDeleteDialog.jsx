/** Confirmation dialog shown before deleting an existing expense. */

import { useTranslation } from 'react-i18next'

import { Button } from '../ui/Button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/Dialog'

/**
 * @param {{
 *   open: boolean,
 *   onOpenChange: (open: boolean) => void,
 *   onConfirm: () => void,
 * }} props
 */
export function ExpenseDeleteDialog({ open, onOpenChange, onConfirm }) {
  const { t } = useTranslation()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('ExpenseForm.DeletePopup.title', 'Delete this expense?')}</DialogTitle>
          <DialogDescription>
            {t(
              'ExpenseForm.DeletePopup.description',
              'Do you really want to delete this expense? This action is irreversible.',
            )}
          </DialogDescription>
        </DialogHeader>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t('ExpenseForm.DeletePopup.cancel', 'Cancel')}
          </Button>
          <Button variant="destructive" onClick={onConfirm}>
            {t('ExpenseForm.DeletePopup.yes', 'Yes')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
