/**
 * Create/edit expense form.
 *
 * The reference splits this across several Radix controls. Here the same
 * behaviours are expressed with plain state and the accessible Select
 * primitive so the ported Playwright helpers keep the same selectors.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useToast } from '../../hooks/useToast'
import { repository } from '../../services/repository'
import { EXPENSE_ERROR_LABELS, expenseFormSchema } from '../../schemas/expense'
import {
  COMMON_CURRENCIES,
  currencyLabel,
  getCurrencyFromGroup,
  majorUnits,
  parseAmount,
} from '../../utils/currency'
import { isIncome } from '../../utils/expenses'
import { Button } from '../ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/Dialog'
import { FormField } from '../ui/Form'
import { Input, Textarea } from '../ui/Input'
import { Select } from '../ui/Select'
import { ReceiptScanButton } from './ReceiptScanButton'

const SPLIT_MODES = /** @type {const} */ ([
  { value: 'EVENLY', label: 'Evenly' },
  { value: 'BY_SHARES', label: 'Unevenly – By shares' },
  { value: 'BY_PERCENTAGE', label: 'Unevenly – By percentage' },
  { value: 'BY_AMOUNT', label: 'Unevenly – By amount' },
])

const RECURRENCES = /** @type {const} */ ([
  { value: 'NONE', label: 'None' },
  { value: 'DAILY', label: 'Daily' },
  { value: 'WEEKLY', label: 'Weekly' },
  { value: 'MONTHLY', label: 'Monthly' },
])

/** @returns {string} */
function today() {
  return new Date().toISOString().slice(0, 10)
}

/** @param {string} groupId @returns {any} */
function readDefaults(groupId) {
  try {
    const raw = localStorage.getItem(`${groupId}-defaultSplittingOptions`)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

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
  const { toast } = useToast()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const editing = Boolean(expense)
  const currency = getCurrencyFromGroup(group)
  const repayment = searchParams.get('reimbursement') === 'yes'

  const defaults = useMemo(() => (editing ? null : readDefaults(group.id)), [editing, group.id])

  const buildPaidFor = useCallback(() => {
    /** @type {Record<string, {checked: boolean, share: string}>} */
    const next = {}
    for (const participant of group.participants || []) {
      next[participant.id] = { checked: true, share: '' }
    }
    if (editing && expense) {
      for (const participant of group.participants || []) {
        const row = (expense.paid_for || []).find(
          (/** @type {any} */ item) => item.participant_id === participant.id,
        )
        if (!row) {
          next[participant.id] = { checked: false, share: '' }
          continue
        }
        let share = ''
        if (expense.split_mode === 'BY_SHARES') share = String(row.shares)
        else if (expense.split_mode === 'BY_PERCENTAGE') share = String(row.shares / 100)
        else if (expense.split_mode === 'BY_AMOUNT') share = majorUnits(row.shares)
        next[participant.id] = { checked: true, share }
      }
      return next
    }
    if (repayment) {
      const from = searchParams.get('from')
      const to = searchParams.get('to')
      for (const participantId of Object.keys(next)) {
        next[participantId] = {
          checked: participantId === to,
          share: '',
        }
      }
      void from
      return next
    }
    if (defaults?.paidFor && Array.isArray(defaults.paidFor)) {
      for (const participantId of Object.keys(next)) {
        next[participantId] = {
          ...next[participantId],
          checked: defaults.paidFor.includes(participantId),
        }
      }
    }
    return next
  }, [group.participants, editing, expense, repayment, searchParams, defaults])

  const [title, setTitle] = useState(
    expense?.title || (repayment ? t('ExpenseForm.reimbursement', 'Reimbursement') : ''),
  )
  const [amountInput, setAmountInput] = useState(() => {
    if (expense) return majorUnits(expense.amount)
    if (repayment) {
      const minor = Number(searchParams.get('amount') || 0)
      return majorUnits(minor)
    }
    return ''
  })
  const [expenseDate, setExpenseDate] = useState(expense?.expense_date || today())
  const [categoryId, setCategoryId] = useState(String(expense?.category_id ?? 0))
  const [paidById, setPaidById] = useState(
    expense?.paid_by_id ||
      (repayment ? searchParams.get('from') : activeUserId) ||
      group.participants?.[0]?.id ||
      '',
  )
  const [splitMode, setSplitMode] = useState(
    expense?.split_mode || defaults?.splitMode || 'EVENLY',
  )
  const [advanced, setAdvanced] = useState(
    (expense?.split_mode || defaults?.splitMode || 'EVENLY') !== 'EVENLY',
  )
  const [paidFor, setPaidFor] = useState(buildPaidFor)
  const [recurrence, setRecurrence] = useState(expense?.recurrence_rule || 'NONE')
  const [notes, setNotes] = useState(expense?.notes || '')
  const [isReimbursement, setIsReimbursement] = useState(
    Boolean(expense?.is_reimbursement || repayment),
  )
  const [selectedCurrency, setSelectedCurrency] = useState(
    expense?.original_currency || group.currency_code || '',
  )
  const [originalAmountInput, setOriginalAmountInput] = useState(
    expense?.original_amount ? majorUnits(expense.original_amount) : '',
  )
  const [conversionRateInput, setConversionRateInput] = useState(
    expense?.conversion_rate ? String(expense.conversion_rate) : '',
  )
  const [originalTouched, setOriginalTouched] = useState(false)
  const [useCustomRate, setUseCustomRate] = useState(Boolean(expense?.conversion_rate))
  const [rateNonce, setRateNonce] = useState(0)
  const [rateState, setRateState] = useState(
    /** @type {{status: 'idle'|'loading'|'success'|'error', rate: number|null, message: string}} */ ({
      status: 'idle',
      rate: null,
      message: '',
    }),
  )
  const [saveDefaults, setSaveDefaults] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [documents, setDocuments] = useState(/** @type {any[]} */ (expense?.documents || []))
  const [pendingFiles, setPendingFiles] = useState(/** @type {File[]} */ ([]))

  const foreign = Boolean(selectedCurrency && selectedCurrency !== group.currency_code)
  const income = isIncome(parseAmount(amountInput))
  const rate = useCustomRate
    ? Number(String(conversionRateInput).replace(',', '.')) || null
    : rateState.rate

  const categoryOptions = categories.map((category) => ({
    value: category.id,
    label: category.name,
  }))
  const currencyOptions = useMemo(() => {
    const codes = new Set(COMMON_CURRENCIES.map((item) => item.code))
    if (group.currency_code) codes.add(group.currency_code)
    if (selectedCurrency) codes.add(selectedCurrency)
    return [...codes].map((code) => ({ value: code, label: currencyLabel(code) }))
  }, [group.currency_code, selectedCurrency])

  // Fetch a rate whenever the foreign currency or the date changes.
  useEffect(() => {
    if (!foreign || useCustomRate || !expenseDate || !group.currency_code) {
      setRateState({ status: 'idle', rate: null, message: '' })
      return undefined
    }
    const controller = new AbortController()
    setRateState({ status: 'loading', rate: null, message: '' })
    fetch(
      `https://api.frankfurter.dev/v1/${expenseDate}?base=${encodeURIComponent(selectedCurrency)}`,
      { signal: controller.signal },
    )
      .then(async (response) => {
        if (!response.ok) throw new Error('rate request failed')
        const payload = await response.json()
        const value = Number(payload?.rates?.[group.currency_code])
        if (!Number.isFinite(value) || value <= 0) throw new Error('no rate')
        setRateState({ status: 'success', rate: value, message: '' })
      })
      .catch((caught) => {
        if (caught && caught.name === 'AbortError') return
        setRateState({
          status: 'error',
          rate: null,
          message: t(
            'ExpenseForm.conversionRateState.error',
            'Oops, we could not get the most recent rates.',
          ),
        })
      })
    return () => controller.abort()
  }, [foreign, useCustomRate, expenseDate, selectedCurrency, group.currency_code, rateNonce, t])

  // Drive the group-currency amount from the foreign amount (or the reverse
  // during a repayment, where the balance amount is authoritative).
  useEffect(() => {
    if (!foreign || !rate || !Number.isFinite(rate)) return
    if (repayment) {
      const amount = parseAmount(amountInput)
      setOriginalAmountInput((amount / rate / 100).toFixed(2))
      return
    }
    // Editing an existing expense keeps its stored group-currency amount
    // until the user actually changes the foreign amount.
    if (editing && !originalTouched) return
    if (originalAmountInput === '') return
    setAmountInput(majorUnits(parseAmount(originalAmountInput) * rate))
    setConversionRateInput(String(rate))
    // amountInput is intentionally omitted: repayment uses it as the source.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [foreign, rate, originalAmountInput, repayment, editing, originalTouched])

  /** @param {string} participantId @param {boolean} checked */
  function setParticipantChecked(participantId, checked) {
    setPaidFor((previous) => ({
      ...previous,
      [participantId]: { ...previous[participantId], checked },
    }))
  }

  /**
   * Seed sensible share inputs when the split mode changes, mirroring the
   * reference form's automatic distribution.
   *
   * @param {string} mode
   */
  function applySplitDefaults(mode) {
    setSplitMode(mode)
    if (mode === 'EVENLY') return
    const checked = (group.participants || []).filter(
      (/** @type {any} */ participant) => paidFor[participant.id]?.checked,
    )
    if (!checked.length) return
    setPaidFor((previous) => {
      const next = { ...previous }
      if (mode === 'BY_SHARES') {
        for (const participant of checked) {
          next[participant.id] = { ...next[participant.id], share: '1' }
        }
        return next
      }
      if (mode === 'BY_PERCENTAGE') {
        const base = Math.floor((10_000 / checked.length)) / 100
        let assigned = 0
        checked.forEach((/** @type {any} */ participant, /** @type {number} */ index) => {
          const value =
            index === checked.length - 1
              ? Number((100 - assigned).toFixed(2))
              : Number(base.toFixed(2))
          assigned += value
          next[participant.id] = { ...next[participant.id], share: String(value) }
        })
        return next
      }
      if (mode === 'BY_AMOUNT') {
        const total = parseAmount(amountInput)
        const cents = Math.floor(total / checked.length)
        checked.forEach((/** @type {any} */ participant, /** @type {number} */ index) => {
          const value =
            index === checked.length - 1 ? total - cents * (checked.length - 1) : cents
          next[participant.id] = { ...next[participant.id], share: majorUnits(value) }
        })
      }
      return next
    })
  }

  /** @param {string} participantId @param {string} value */
  function setParticipantShare(participantId, value) {
    setPaidFor((previous) => ({
      ...previous,
      [participantId]: { ...previous[participantId], share: value },
    }))
  }

  /** @returns {string[]} */
  function validate() {
    const parsed = expenseFormSchema.safeParse({
      title,
      amount: amountInput,
      expenseDate,
      categoryId,
      paidById,
      splitMode,
      recurrence,
      paidFor: (group.participants || []).map((/** @type {any} */ participant) => ({
        participant_id: participant.id,
        checked: Boolean(paidFor[participant.id]?.checked),
        share: String(paidFor[participant.id]?.share ?? ''),
      })),
      originalCurrency: selectedCurrency,
      originalAmount: originalAmountInput,
      conversionRate: conversionRateInput,
      notes,
    })
    if (!parsed.success) {
      return parsed.error.issues.map(
        (issue) => EXPENSE_ERROR_LABELS[issue.message] || issue.message,
      )
    }

    /** @type {string[]} */
    const errors = []
    const amount = parseAmount(amountInput)
    const checked = (group.participants || []).filter(
      (/** @type {any} */ participant) => paidFor[participant.id]?.checked,
    )
    if (splitMode === 'BY_PERCENTAGE') {
      const total = checked.reduce(
        (/** @type {number} */ sum, /** @type {any} */ participant) =>
          sum + (Number(String(paidFor[participant.id]?.share ?? '').replace(',', '.')) || 0),
        0,
      )
      if (Math.abs(total - 100) > 0.0001) errors.push('Sum of percentages must equal 100.')
    }
    if (splitMode === 'BY_AMOUNT') {
      const total = checked.reduce(
        (/** @type {number} */ sum, /** @type {any} */ participant) =>
          sum + parseAmount(paidFor[participant.id]?.share ?? ''),
        0,
      )
      if (total !== amount) errors.push('The sum of amounts must equal the total amount.')
    }
    return errors
  }

  /** @param {React.FormEvent} event */
  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    const errors = validate()
    if (errors.length) {
      setError(errors[0])
      return
    }
    setPending(true)
    try {
      const checked = (group.participants || []).filter(
        (/** @type {any} */ participant) => paidFor[participant.id]?.checked,
      )
      const paidForPayload = checked.map((/** @type {any} */ participant) => {
        const raw = paidFor[participant.id]?.share ?? ''
        if (splitMode === 'BY_AMOUNT') {
          return { participant_id: participant.id, amount: parseAmount(raw) }
        }
        if (splitMode === 'BY_PERCENTAGE') {
          return {
            participant_id: participant.id,
            shares: Number(String(raw).replace(',', '.')) || 0,
          }
        }
        if (splitMode === 'BY_SHARES') {
          return {
            participant_id: participant.id,
            shares: Number(String(raw).replace(',', '.')) || 0,
          }
        }
        return { participant_id: participant.id, shares: 1 }
      })

      const payload = {
        expense_date: expenseDate,
        title: title.trim(),
        category_id: Number(categoryId) || 0,
        amount: parseAmount(amountInput),
        original_amount: foreign ? parseAmount(originalAmountInput) : null,
        original_currency: foreign ? selectedCurrency : null,
        conversion_rate: foreign && rate ? String(rate) : null,
        paid_by_id: paidById,
        is_reimbursement: isReimbursement,
        split_mode: splitMode,
        notes: notes || null,
        recurrence_rule: recurrence,
        paid_for: paidForPayload,
        participant_id: activeUserId,
      }

      let saved
      if (editing && expense) {
        saved = await repository.expenses.update(group.id, expense.id, payload)
      } else {
        saved = await repository.expenses.create(group.id, payload)
      }

      // New expenses can only receive documents once they exist; upload the
      // staged files immediately after creation (queued uploads arrive in M2).
      if (!editing && saved && pendingFiles.length) {
        for (const file of pendingFiles) {
          try {
            await repository.documents.upload(group.id, saved.id, file)
          } catch {
            toast({
              title: t('ExpenseDocumentsInput.ErrorToast.title', 'Error while uploading document'),
              description: t(
                'ExpenseDocumentsInput.ErrorToast.description',
                'Something wrong happened when uploading the document. Please retry later or select a different file.',
              ),
            })
          }
        }
      }

      if (saveDefaults) {
        try {
          localStorage.setItem(
            `${group.id}-defaultSplittingOptions`,
            JSON.stringify({
              splitMode,
              paidFor: checked.map((/** @type {any} */ participant) => participant.id),
            }),
          )
        } catch {
          // Storage is optional.
        }
      }

      navigate(`/groups/${group.id}/expenses`)
      void saved
    } catch (caught) {
      const detail =
        caught && typeof caught === 'object' && 'detail' in caught
          ? String(caught.detail)
          : 'Could not save the expense.'
      setError(detail)
      toast({ title: t('ExpenseForm.saveError', 'Could not save the expense'), description: detail })
    } finally {
      setPending(false)
    }
  }

  async function handleDelete() {
    if (!expense) return
    setPending(true)
    try {
      await repository.expenses.remove(group.id, expense.id)
      navigate(`/groups/${group.id}/expenses`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not delete the expense.')
    } finally {
      setPending(false)
      setDeleteOpen(false)
    }
  }

  /** @param {React.ChangeEvent<HTMLInputElement>} event */
  async function handleDocuments(event) {
    const files = [...(event.target.files || [])]
    if (!files.length) return
    if (!editing || !expense) {
      setPendingFiles((previous) => [...previous, ...files])
      return
    }
    for (const file of files) {
      try {
        const document = await repository.documents.upload(group.id, expense.id, file)
        setDocuments((previous) => [...previous, document])
      } catch (caught) {
        toast({
          title: t('ExpenseDocumentsInput.ErrorToast.title', 'Error while uploading document'),
          description:
            caught instanceof Error
              ? caught.message
              : t(
                  'ExpenseDocumentsInput.ErrorToast.description',
                  'Something wrong happened when uploading the document. Please retry later or select a different file.',
                ),
        })
      }
    }
  }

  /** @param {string} documentId */
  async function removeDocument(documentId) {
    if (!expense) return
    try {
      await repository.documents.remove(group.id, expense.id, documentId)
      setDocuments((previous) =>
        previous.filter((/** @type {any} */ document) => document.id !== documentId),
      )
    } catch {
      // Leave the document in place; the server is authoritative.
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">
          {income
            ? editing
              ? t('ExpenseForm.Income.edit', 'Edit income')
              : t('ExpenseForm.Income.create', 'Create income')
            : editing
              ? t('ExpenseForm.Expense.edit', 'Edit expense')
              : t('ExpenseForm.Expense.create', 'Create expense')}
        </h2>
        <ReceiptScanButton
          groupId={group.id}
          features={features}
          onExtracted={(result) => {
            if (result.title) setTitle(result.title)
            if (result.amount) setAmountInput(majorUnits(Math.round(result.amount * 100)))
            if (result.date) setExpenseDate(result.date)
            if (result.category_id) setCategoryId(String(result.category_id))
          }}
        />
      </div>

      {error ? (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </p>
      ) : null}

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
              options={(group.participants || []).map((/** @type {any} */ participant) => ({
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

      <Card>
        <CardHeader>
          <CardTitle>
            {t('ExpenseForm.Expense.paidFor.title', 'Paid for')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="mb-2 flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                setPaidFor((previous) =>
                  Object.fromEntries(
                    Object.entries(previous).map(([id, value]) => [id, { ...value, checked: true }]),
                  ),
                )
              }
            >
              {t('ExpenseForm.selectAll', 'Select all')}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                setPaidFor((previous) =>
                  Object.fromEntries(
                    Object.entries(previous).map(([id, value]) => [id, { ...value, checked: false }]),
                  ),
                )
              }
            >
              {t('ExpenseForm.selectNone', 'Select none')}
            </Button>
          </div>
          <ul className="flex flex-col divide-y divide-border">
            {(group.participants || []).map((/** @type {any} */ participant) => {
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
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAdvanced((value) => !value)}
            >
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

      <Card>
        <CardHeader>
          <CardTitle>{t('ExpenseForm.Expense.currencyField.label', 'Currency of expense')}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <FormField
            label={t('ExpenseForm.Expense.currencyField.label', 'Currency of expense')}
            htmlFor="expense-currency"
          >
            <Select
              id="expense-currency"
              value={selectedCurrency}
              options={currencyOptions}
              onChange={setSelectedCurrency}
            />
          </FormField>

          {foreign ? (
            <>
              <FormField
                label={
                  repayment
                    ? t('ExpenseForm.originalAmountField.repaymentLabel', 'Amount to transfer')
                    : t('ExpenseForm.originalAmountField.label', 'Amount to convert')
                }
                htmlFor="expense-original-amount"
              >
                <Input
                  id="expense-original-amount"
                  name="originalAmount"
                  inputMode="decimal"
                  value={originalAmountInput}
                  readOnly={repayment}
                  onChange={(event) => {
                    setOriginalTouched(true)
                    setOriginalAmountInput(event.target.value)
                  }}
                />
              </FormField>
              <div className="sm:col-span-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                {rateState.status === 'loading' ? (
                  <span>{t('ExpenseForm.conversionRateState.loading', 'Getting exchange rates…')}</span>
                ) : rate ? (
                  <span>
                    {selectedCurrency} 1 = {group.currency_code} {Number(rate).toFixed(2)}
                  </span>
                ) : (
                  <span>
                    {rateState.message ||
                      t('ExpenseForm.conversionRateState.noRate', 'Enter a custom rate below.')}
                  </span>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setUseCustomRate((value) => !value)}
                >
                  {useCustomRate
                    ? t('ExpenseForm.conversionRateField.useApi', 'Use rates from Frankfurter')
                    : t('ExpenseForm.conversionRateField.useCustom', 'Use custom rate')}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRateNonce((value) => value + 1)}
                >
                  {t('ExpenseForm.conversionRateState.refresh', 'Refresh')}
                </Button>
              </div>
              {useCustomRate ? (
                <FormField
                  label={t('ExpenseForm.conversionRateField.label', 'Exchange rate')}
                  htmlFor="expense-rate"
                >
                  <Input
                    id="expense-rate"
                    name="conversionRate"
                    inputMode="decimal"
                    value={conversionRateInput}
                    onChange={(event) => setConversionRateInput(event.target.value)}
                  />
                </FormField>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>

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
                {documents.map((/** @type {any} */ document) => (
                  <li key={document.id} className="flex items-center justify-between gap-2">
                    <a href={document.url} target="_blank" rel="noreferrer" className="underline">
                      {document.id}
                    </a>
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
          <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
            {t('ExpenseForm.DeletePopup.label', 'Delete')}
          </Button>
        ) : null}
        <Button variant="ghost" onClick={() => navigate(`/groups/${group.id}/expenses`)}>
          {t('ExpenseForm.cancel', 'Cancel')}
        </Button>
        <span className="ml-auto self-center text-xs text-muted-foreground">
          {currency.code ? `${currency.code} · ${i18n.resolvedLanguage}` : currency.symbol}
        </span>
      </div>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
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
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              {t('ExpenseForm.DeletePopup.cancel', 'Cancel')}
            </Button>
            <Button variant="destructive" onClick={() => void handleDelete()}>
              {t('ExpenseForm.DeletePopup.yes', 'Yes')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </form>
  )
}
