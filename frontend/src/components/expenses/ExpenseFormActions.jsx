/** Submit, delete and cancel buttons for the expense form. */

import { useTranslation } from 'react-i18next'

import { Button } from '../ui/Button'

/**
 * @param {{
 *   pending: boolean,
 *   editing: boolean,
 *   onDelete: () => void,
 *   onCancel: () => void,
 *   currency: {code: string, symbol: string},
 *   language: string,
 * }} props
 */
export function ExpenseFormActions({ pending, editing, onDelete, onCancel, currency, language }) {
  const { t } = useTranslation()

  return (
    <div className="flex flex-wrap gap-2">
      <Button type="submit" disabled={pending}>
        {pending
          ? editing
            ? t('ExpenseForm.saving', 'Saving…')
            : t('ExpenseForm.creating', 'Creating…')
          : editing
            ? t('ExpenseForm.save', 'Save')
            : t('ExpenseForm.create', 'Create')}
      </Button>
      {editing ? (
        <Button variant="destructive" onClick={onDelete}>
          {t('ExpenseForm.DeletePopup.label', 'Delete')}
        </Button>
      ) : null}
      <Button variant="ghost" onClick={onCancel}>
        {t('ExpenseForm.cancel', 'Cancel')}
      </Button>
      <span className="ml-auto self-center text-xs text-muted-foreground">
        {currency.code ? `${currency.code} · ${language}` : currency.symbol}
      </span>
    </div>
  )
}
