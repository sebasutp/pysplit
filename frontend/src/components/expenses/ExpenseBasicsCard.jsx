/** Title, amount, date, category, payer and recurrence fields. */

import { useTranslation } from 'react-i18next'

import { Card, CardContent } from '../ui/Card'
import { FormField } from '../ui/Form'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'

const RECURRENCES = /** @type {const} */ ([
  { value: 'NONE', label: 'None' },
  { value: 'DAILY', label: 'Daily' },
  { value: 'WEEKLY', label: 'Weekly' },
  { value: 'MONTHLY', label: 'Monthly' },
])

/**
 * @param {{
 *   title: string,
 *   setTitle: (value: string) => void,
 *   amountInput: string,
 *   setAmountInput: (value: string) => void,
 *   expenseDate: string,
 *   setExpenseDate: (value: string) => void,
 *   categoryId: string,
 *   setCategoryId: (value: string) => void,
 *   categoryOptions: {value: string|number, label: string}[],
 *   paidById: string,
 *   setPaidById: (value: string) => void,
 *   participants: any[],
 *   recurrence: string,
 *   setRecurrence: (value: string) => void,
 *   income: boolean,
 *   foreign: boolean,
 *   repayment: boolean,
 * }} props
 */
export function ExpenseBasicsCard({
  title,
  setTitle,
  amountInput,
  setAmountInput,
  expenseDate,
  setExpenseDate,
  categoryId,
  setCategoryId,
  categoryOptions,
  paidById,
  setPaidById,
  participants,
  recurrence,
  setRecurrence,
  income,
  foreign,
  repayment,
}) {
  const { t } = useTranslation()

  return (
    <Card>
      <CardContent className="grid gap-4 pt-5 sm:grid-cols-2">
        <FormField
          label={
            income
              ? t('ExpenseForm.Income.TitleField.label', 'Income title')
              : t('ExpenseForm.Expense.TitleField.label', 'Expense title')
          }
          htmlFor="expense-title"
        >
          <Input
            id="expense-title"
            name="title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder={t('ExpenseForm.Expense.TitleField.placeholder', 'Monday evening restaurant')}
          />
        </FormField>

        <FormField label={t('ExpenseForm.amountField.label', 'Amount')} htmlFor="expense-amount">
          <Input
            id="expense-amount"
            name="amount"
            inputMode="decimal"
            value={amountInput}
            readOnly={foreign && !repayment}
            onChange={(event) => setAmountInput(event.target.value)}
          />
        </FormField>

        <FormField
          label={
            income
              ? t('ExpenseForm.Income.DateField.label', 'Income date')
              : t('ExpenseForm.Expense.DateField.label', 'Expense date')
          }
          htmlFor="expense-date"
        >
          <Input
            id="expense-date"
            name="expenseDate"
            type="date"
            value={expenseDate}
            onChange={(event) => setExpenseDate(event.target.value)}
          />
        </FormField>

        <FormField label={t('ExpenseForm.categoryField.label', 'Category')} htmlFor="expense-category">
          <Select
            id="expense-category"
            value={categoryId}
            options={categoryOptions}
            onChange={setCategoryId}
          />
        </FormField>

        <FormField
          label={
            income
              ? t('ExpenseForm.Income.paidByField.label', 'Received by')
              : t('ExpenseForm.Expense.paidByField.label', 'Paid by')
          }
          htmlFor="expense-paid-by"
        >
          <Select
            id="expense-paid-by"
            testId="paid-by"
            value={paidById}
            options={participants.map((participant) => ({
              value: participant.id,
              label: participant.name,
            }))}
            onChange={setPaidById}
          />
        </FormField>

        <FormField
          label={t('ExpenseForm.Expense.recurrenceRule.label', 'Expense Recurrence')}
          htmlFor="expense-recurrence"
        >
          <Select
            id="expense-recurrence"
            value={recurrence}
            options={RECURRENCES.map((item) => ({
              value: item.value,
              label: t(`ExpenseForm.Expense.recurrenceRule.${item.value.toLowerCase()}`, item.label),
            }))}
            onChange={setRecurrence}
          />
        </FormField>
      </CardContent>
    </Card>
  )
}
