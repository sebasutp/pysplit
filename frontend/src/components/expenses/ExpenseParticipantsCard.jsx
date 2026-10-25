/** Participant selection and split-mode controls. */

import { useTranslation } from 'react-i18next'

import { Button } from '../ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { FormField } from '../ui/Form'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'

const SPLIT_MODES = /** @type {const} */ ([
  { value: 'EVENLY', label: 'Evenly' },
  { value: 'BY_SHARES', label: 'Unevenly – By shares' },
  { value: 'BY_PERCENTAGE', label: 'Unevenly – By percentage' },
  { value: 'BY_AMOUNT', label: 'Unevenly – By amount' },
])

/**
 * @param {{
 *   participants: any[],
 *   paidFor: Record<string, {checked: boolean, share: string}>,
 *   splitMode: string,
 *   advanced: boolean,
 *   saveDefaults: boolean,
 *   setSaveDefaults: (value: boolean) => void,
 *   setParticipantChecked: (participantId: string, checked: boolean) => void,
 *   setParticipantShare: (participantId: string, value: string) => void,
 *   setAllChecked: (checked: boolean) => void,
 *   applySplitDefaults: (mode: string) => void,
 *   toggleAdvanced: () => void,
 *   group: any,
 * }} props
 */
export function ExpenseParticipantsCard({
  participants,
  paidFor,
  splitMode,
  advanced,
  saveDefaults,
  setSaveDefaults,
  setParticipantChecked,
  setParticipantShare,
  setAllChecked,
  applySplitDefaults,
  toggleAdvanced,
  group,
}) {
  const { t } = useTranslation()

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('ExpenseForm.Expense.paidFor.title', 'Paid for')}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="mb-2 flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => setAllChecked(true)}>
            {t('ExpenseForm.selectAll', 'Select all')}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setAllChecked(false)}>
            {t('ExpenseForm.selectNone', 'Select none')}
          </Button>
        </div>
        <ul className="flex flex-col divide-y divide-border">
          {participants.map((participant) => {
            const row = paidFor[participant.id] || { checked: false, share: '' }
            return (
              <li
                key={participant.id}
                data-id={participant.id}
                className="flex items-center justify-between gap-3 py-2"
              >
                <label className="flex flex-1 items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    aria-label={participant.name}
                    aria-checked={row.checked ? 'true' : 'false'}
                    checked={row.checked}
                    onChange={(event) =>
                      setParticipantChecked(participant.id, event.target.checked)
                    }
                  />
                  <span>{participant.name}</span>
                </label>
                {advanced && splitMode !== 'EVENLY' && row.checked ? (
                  <div className="flex items-center gap-1">
                    <Input
                      type="text"
                      inputMode="decimal"
                      aria-label={`${participant.name} share`}
                      className="h-8 w-24 text-right"
                      value={row.share}
                      onChange={(event) =>
                        setParticipantShare(participant.id, event.target.value)
                      }
                    />
                    <span className="text-xs text-muted-foreground">
                      {splitMode === 'BY_SHARES'
                        ? t('ExpenseForm.shares', 'share(s)')
                        : splitMode === 'BY_PERCENTAGE'
                          ? '%'
                          : group.currency}
                    </span>
                  </div>
                ) : null}
              </li>
            )
          })}
        </ul>

        <div className="mt-4">
          <Button variant="outline" size="sm" onClick={toggleAdvanced}>
            {t('ExpenseForm.advancedOptions', 'Advanced splitting options…')}
          </Button>
        </div>

        {advanced ? (
          <div className="mt-3 grid gap-4 rounded-md border border-border p-3 sm:grid-cols-2">
            <FormField label={t('ExpenseForm.SplitModeField.label', 'Split mode')} htmlFor="split-mode">
              <Select
                id="split-mode"
                testId="split-mode"
                value={splitMode}
                options={SPLIT_MODES.map((item) => ({
                  value: item.value,
                  label:
                    item.value === 'EVENLY'
                      ? t('ExpenseForm.SplitModeField.evenly', item.label)
                      : item.value === 'BY_SHARES'
                        ? t('ExpenseForm.SplitModeField.byShares', item.label)
                        : item.value === 'BY_PERCENTAGE'
                          ? t('ExpenseForm.SplitModeField.byPercentage', item.label)
                          : t('ExpenseForm.SplitModeField.byAmount', item.label),
                }))}
                onChange={applySplitDefaults}
              />
            </FormField>
            <label className="flex items-end gap-2 pb-2 text-sm">
              <input
                type="checkbox"
                checked={saveDefaults}
                onChange={(event) => setSaveDefaults(event.target.checked)}
              />
              {t('ExpenseForm.SplitModeField.saveAsDefault', 'Save as default splitting options')}
            </label>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
