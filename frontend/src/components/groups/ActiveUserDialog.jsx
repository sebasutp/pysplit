/**
 * "Who are you?" modal shown on a group's first visit in this browser.
 *
 * It mirrors the reference behaviour: the answer is stored as
 * `<groupId>-activeUser` so expense cards and statistics can personalise.
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '../ui/Button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/Dialog'

/**
 * @param {{
 *   open: boolean,
 *   participants: {id: string, name: string}[],
 *   initialValue: string|null,
 *   onSave: (participantId: string|null) => void,
 *   onOpenChange: (open: boolean) => void,
 * }} props
 */
export function ActiveUserDialog({
  open,
  participants,
  initialValue,
  onSave,
  onOpenChange,
}) {
  const { t } = useTranslation()
  const [value, setValue] = useState(initialValue || '')

  useEffect(() => {
    if (open) setValue(initialValue || '')
  }, [open, initialValue])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('Expenses.ActiveUserModal.title', 'Who are you?')}</DialogTitle>
          <DialogDescription>
            {t(
              'Expenses.ActiveUserModal.description',
              'Tell us which participant you are to let us customize how the information is displayed.',
            )}
          </DialogDescription>
        </DialogHeader>
        <div role="radiogroup" className="my-4 flex flex-col gap-2">
          {participants.map((participant) => (
            <label key={participant.id} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="active-user"
                value={participant.id}
                checked={value === participant.id}
                onChange={() => setValue(participant.id)}
              />
              {participant.name}
            </label>
          ))}
          <button
            type="button"
            className="mt-1 text-left text-sm text-muted-foreground hover:text-foreground"
            onClick={() => setValue('')}
          >
            {t(
              'Expenses.ActiveUserModal.nobody',
              'I don’t want to select anyone',
            )}
          </button>
        </div>
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            {t(
              'Expenses.ActiveUserModal.footer',
              'This setting can be changed later in the group settings.',
            )}
          </p>
          <Button onClick={() => onSave(value || null)}>
            {t('Expenses.ActiveUserModal.save', 'Save changes')}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
