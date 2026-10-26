/**
 * Create/edit expense form.
 *
 * State and derived values live in `useExpenseForm`; the cards below are small
 * presentational components so this file only composes them. The accessible
 * Select primitive keeps the ported Playwright selectors stable.
 */

import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useExpenseForm } from '../../hooks/useExpenseForm'
import { ReceiptScanButton } from './ReceiptScanButton'
import { ExpenseBasicsCard } from './ExpenseBasicsCard'
import { ExpenseParticipantsCard } from './ExpenseParticipantsCard'
import { ExpenseCurrencyCard } from './ExpenseCurrencyCard'
import { ExpenseDocumentsCard } from './ExpenseDocumentsCard'
import { ExpenseFormActions } from './ExpenseFormActions'
import { ExpenseDeleteDialog } from './ExpenseDeleteDialog'
import { Button } from '../ui/Button'

/**
 * @param {{
 *   group: any,
 *   categories: any[],
 *   expense?: any|null,
 *   activeUserId?: string|null,
 *   features?: any,
 * }} props
 */
export function ExpenseForm({ group, categories, expense = null, activeUserId = null, features = {} }) {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const form = useExpenseForm({ group, categories, expense, activeUserId })
  const participants = group.participants || []

  return (
    <form onSubmit={form.handleSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">
          {form.income
            ? form.editing
              ? t('ExpenseForm.Income.edit', 'Edit income')
              : t('ExpenseForm.Income.create', 'Create income')
            : form.editing
              ? t('ExpenseForm.Expense.edit', 'Edit expense')
              : t('ExpenseForm.Expense.create', 'Create expense')}
        </h2>
        <ReceiptScanButton
          groupId={group.id}
          features={features}
          onExtracted={form.applyExtracted}
        />
      </div>

      {form.error ? (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {form.error}
        </p>
      ) : null}

      {form.pendingReceiptTotal ? (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-sm"
        >
          <span>
            {t(
              'ExpenseForm.pendingReceiptTotal',
              'A receipt scanned while offline is ready.',
            )}
          </span>
          <span className="flex gap-2">
            <Button type="button" size="sm" onClick={form.applyPendingReceiptTotal}>
              {t('ExpenseForm.pendingReceiptTotalApply', 'Use scanned total')}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={form.dismissPendingReceiptTotal}
            >
              {t('ExpenseForm.pendingReceiptTotalDismiss', 'Dismiss')}
            </Button>
          </span>
        </div>
      ) : null}

      <ExpenseBasicsCard
        title={form.title}
        setTitle={form.setTitle}
        amountInput={form.amountInput}
        setAmountInput={form.setAmountInput}
        expenseDate={form.expenseDate}
        setExpenseDate={form.setExpenseDate}
        categoryId={form.categoryId}
        setCategoryId={form.setCategoryId}
        categoryOptions={form.categoryOptions}
        paidById={form.paidById}
        setPaidById={form.setPaidById}
        participants={participants}
        recurrence={form.recurrence}
        setRecurrence={form.setRecurrence}
        income={form.income}
        foreign={form.foreign}
        repayment={form.repayment}
      />

      <ExpenseParticipantsCard
        participants={participants}
        paidFor={form.paidFor}
        splitMode={form.splitMode}
        advanced={form.advanced}
        saveDefaults={form.saveDefaults}
        setSaveDefaults={form.setSaveDefaults}
        setParticipantChecked={form.setParticipantChecked}
        setParticipantShare={form.setParticipantShare}
        setAllChecked={form.setAllChecked}
        applySplitDefaults={form.applySplitDefaults}
        toggleAdvanced={form.toggleAdvanced}
        group={group}
      />

      <ExpenseCurrencyCard
        selectedCurrency={form.selectedCurrency}
        setSelectedCurrency={form.setSelectedCurrency}
        currencyOptions={form.currencyOptions}
        foreign={form.foreign}
        repayment={form.repayment}
        originalAmountInput={form.originalAmountInput}
        updateOriginalAmount={form.updateOriginalAmount}
        conversionRateInput={form.conversionRateInput}
        setConversionRateInput={form.setConversionRateInput}
        useCustomRate={form.useCustomRate}
        toggleCustomRate={form.toggleCustomRate}
        refreshRate={form.refreshRate}
        rateState={form.rateState}
        rate={form.rate}
        group={group}
      />

      <ExpenseDocumentsCard
        notes={form.notes}
        setNotes={form.setNotes}
        isReimbursement={form.isReimbursement}
        setIsReimbursement={form.setIsReimbursement}
        handleDocuments={form.handleDocuments}
        pendingFiles={form.pendingFiles}
        documents={form.documents}
        removeDocument={form.removeDocument}
      />

      <ExpenseFormActions
        pending={form.pending}
        editing={form.editing}
        onDelete={() => form.setDeleteOpen(true)}
        onCancel={() => navigate(`/groups/${group.id}/expenses`)}
        currency={form.currency}
        language={i18n.resolvedLanguage || i18n.language || ''}
      />

      <ExpenseDeleteDialog
        open={form.deleteOpen}
        onOpenChange={form.setDeleteOpen}
        onConfirm={() => void form.handleDelete()}
      />
    </form>
  )
}
