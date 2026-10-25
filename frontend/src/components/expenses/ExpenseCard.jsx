/** One expense row in the group's expense list. */

import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { balanceForParticipant, categoryIcon, paidForLabel } from '../../utils/expenses'
import { formatCurrency, getCurrencyFromGroup } from '../../utils/currency'

/**
 * @param {{
 *   expense: any,
 *   participants: {id: string, name: string}[],
 *   categories: any[],
 *   group: any,
 *   activeUserId: string|null,
 *   locale: string,
 * }} props
 */
export function ExpenseCard({ expense, participants, categories, group, activeUserId, locale }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const currency = getCurrencyFromGroup(group)
  const category = categories.find((item) => item.id === expense.category_id)
  const paidBy =
    participants.find((participant) => participant.id === expense.paid_by_id)?.name || '—'
  const forLabel = paidForLabel(expense.paid_for, participants)
  const income = expense.amount < 0
  const balance = balanceForParticipant(expense, activeUserId)
  const involved =
    Boolean(activeUserId) &&
    (expense.paid_by_id === activeUserId ||
      (expense.paid_for || []).some(
        (/** @type {any} */ row) => row.participant_id === activeUserId,
      ))
  const original =
    expense.original_amount !== null &&
    expense.original_amount !== undefined &&
    expense.original_currency &&
    expense.original_currency !== group.currency_code

  return (
    <div
      data-testid="expense-card"
      data-expense-id={expense.id}
      role="button"
      tabIndex={0}
      className="cursor-pointer rounded-lg border border-border bg-card p-3 shadow-sm transition-colors hover:bg-accent/40"
      onClick={() => navigate(`/groups/${group.id}/expenses/${expense.id}/edit`)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          navigate(`/groups/${group.id}/expenses/${expense.id}/edit`)
        }
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span aria-hidden="true" className="text-base">
              {categoryIcon(category)}
            </span>
            <p className="truncate font-medium">{expense.title}</p>
            {category ? (
              <span className="hidden rounded-full bg-secondary px-2 py-0.5 text-[11px] text-secondary-foreground sm:inline">
                {category.name}
              </span>
            ) : null}
            {expense.is_reimbursement ? (
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
                {t('ExpenseForm.reimbursement', 'Reimbursement')}
              </span>
            ) : null}
            {expense.receipt ? (
              <span aria-hidden="true" title={t('ReceiptItems.title', 'Receipt items')}>
                🧾
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {income
              ? t('ExpenseCard.receivedByPlain', 'Received by {{paidBy}} for {{paidFor}}', {
                  paidBy,
                  paidFor: forLabel,
                })
              : t('ExpenseCard.paidByPlain', 'Paid by {{paidBy}} for {{paidFor}}', {
                  paidBy,
                  paidFor: forLabel,
                })}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">{expense.expense_date}</p>
          {Array.isArray(expense.documents) && expense.documents.length ? (
            <p className="mt-0.5 text-xs text-muted-foreground">
              📎 {expense.documents.length}
            </p>
          ) : null}
        </div>
        <div className="flex-shrink-0 text-right">
          <p
            className={`font-semibold tabular-nums ${
              income ? 'text-green-600' : ''
            }`}
          >
            {formatCurrency(currency, expense.amount, locale)}
          </p>
          {original ? (
            <p className="text-xs text-muted-foreground">
              {formatCurrency(
                { code: expense.original_currency, symbol: expense.original_currency },
                expense.original_amount,
                locale,
              )}
            </p>
          ) : null}
          {involved ? (
            <p className="mt-1 text-xs text-muted-foreground">
              {t('ExpenseCard.yourBalance', 'Your balance:')}{' '}
              <span className="font-medium text-foreground">
                {formatCurrency(currency, balance || 0, locale)}
              </span>
            </p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
