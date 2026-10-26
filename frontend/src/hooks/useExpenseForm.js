/**
 * State, derived values and submit logic for the create/edit expense form.
 *
 * Keeping this out of the component makes the render tree small and gives the
 * currency/repayment derivations a single place to live.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useToast } from './useToast'
import { repository } from '../services/repository'
import { EXPENSE_ERROR_LABELS, expenseFormSchema } from '../schemas/expense'
import {
  COMMON_CURRENCIES,
  currencyLabel,
  getCurrencyFromGroup,
  majorUnits,
  parseAmount,
} from '../utils/currency'
import { isIncome } from '../utils/expenses'

/**
 * Format a Date as a `yyyy-mm-dd` string using the local calendar date.
 *
 * `toISOString()` converts to UTC first, so it reports tomorrow for users west
 * of UTC during the evening. The date input expects the local date.
 *
 * @param {Date} [date]
 * @returns {string}
 */
export function localDateString(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** @returns {string} */
export function today() {
  return localDateString()
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
 * }} props
 */
export function useExpenseForm({ group, categories, expense = null, activeUserId = null }) {
  const { t } = useTranslation()
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
      const to = searchParams.get('to')
      for (const participantId of Object.keys(next)) {
        next[participantId] = {
          checked: participantId === to,
          share: '',
        }
      }
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
  const [pendingReceiptTotal, setPendingReceiptTotal] = useState(
    /** @type {any|null} */ (null),
  )

  // A total-only scan queued offline is extracted after reconnect, when its
  // original form is gone. Offer the result on the next new expense instead of
  // leaving it in metadata that nothing reads.
  useEffect(() => {
    if (editing || !group.id) return undefined
    let cancelled = false
    repository.receipts
      .pendingTotal(group.id)
      .then((value) => {
        if (!cancelled) setPendingReceiptTotal(value)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [editing, group.id])

  const foreign = Boolean(selectedCurrency && selectedCurrency !== group.currency_code)
  const income = isIncome(parseAmount(amountInput))
  const rate = useCustomRate
    ? Number(String(conversionRateInput).replace(',', '.')) || null
    : rateState.rate

  // During a repayment the group-currency amount is authoritative (it comes
  // from the balance), so the foreign "Amount to transfer" is purely derived.
  // Deriving it at render time keeps it in sync when the amount is edited after
  // the rate has already been fetched.
  const repaymentOriginal =
    repayment && foreign && rate && Number.isFinite(rate)
      ? (parseAmount(amountInput) / rate / 100).toFixed(2)
      : null
  const displayedOriginalAmount = repaymentOriginal ?? originalAmountInput

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

  // Drive the group-currency amount from the foreign amount. Repayments are
  // handled by the render-time derivation above.
  useEffect(() => {
    if (repayment) return
    if (!foreign || !rate || !Number.isFinite(rate)) return
    // Editing an existing expense keeps its stored group-currency amount
    // until the user actually changes the foreign amount.
    if (editing && !originalTouched) return
    if (originalAmountInput === '') return
    setAmountInput(majorUnits(parseAmount(originalAmountInput) * rate))
    setConversionRateInput(String(rate))
  }, [foreign, rate, originalAmountInput, repayment, editing, originalTouched])

  /** @param {string} participantId @param {boolean} checked */
  function setParticipantChecked(participantId, checked) {
    setPaidFor((previous) => ({
      ...previous,
      [participantId]: { ...previous[participantId], checked },
    }))
  }

  /** @param {boolean} checked */
  function setAllChecked(checked) {
    setPaidFor((previous) =>
      Object.fromEntries(
        Object.entries(previous).map(([id, value]) => [id, { ...value, checked }]),
      ),
    )
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
        const base = Math.floor(10_000 / checked.length) / 100
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

  /** @param {string} value */
  function updateOriginalAmount(value) {
    setOriginalTouched(true)
    setOriginalAmountInput(value)
  }

  /** @param {any} result */
  function applyExtracted(result) {
    if (result.title) setTitle(result.title)
    if (result.amount) setAmountInput(majorUnits(Math.round(result.amount * 100)))
    if (result.date) setExpenseDate(result.date)
    if (result.category_id) setCategoryId(String(result.category_id))
  }

  function consumePendingReceiptTotal() {
    setPendingReceiptTotal(null)
    void repository.receipts.clearPendingTotal(group.id).catch(() => {})
  }

  function applyPendingReceiptTotal() {
    if (!pendingReceiptTotal) return
    applyExtracted(pendingReceiptTotal)
    consumePendingReceiptTotal()
  }

  function dismissPendingReceiptTotal() {
    consumePendingReceiptTotal()
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
      originalAmount: displayedOriginalAmount,
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

      /** @type {Record<string, any>} */
      const payload = {
        expense_date: expenseDate,
        title: title.trim(),
        category_id: Number(categoryId) || 0,
        amount: parseAmount(amountInput),
        original_amount: foreign ? parseAmount(displayedOriginalAmount) : null,
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
        // Optimistic concurrency: tell the API which version we loaded so a
        // concurrent edit is rejected with a 409 instead of silently overwritten.
        if (typeof expense.version === 'number') payload.base_version = expense.version
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
      const conflict =
        caught !== null &&
        typeof caught === 'object' &&
        'code' in caught &&
        caught.code === 'conflict'
      if (conflict) {
        const message = t(
          'ExpenseForm.conflict',
          'This expense was changed by someone else. Reload the page and try again.',
        )
        // Keep the user's values on screen: never retry or overwrite blindly.
        setError(message)
        toast({
          title: t('ExpenseForm.conflictTitle', 'Expense changed elsewhere'),
          description: message,
        })
        return
      }
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

  return {
    editing,
    repayment,
    currency,
    foreign,
    income,
    rate,
    rateState,
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
    splitMode,
    applySplitDefaults,
    advanced,
    toggleAdvanced: () => setAdvanced((value) => !value),
    paidFor,
    setParticipantChecked,
    setParticipantShare,
    setAllChecked,
    recurrence,
    setRecurrence,
    notes,
    setNotes,
    isReimbursement,
    setIsReimbursement,
    selectedCurrency,
    setSelectedCurrency,
    currencyOptions,
    originalAmountInput: displayedOriginalAmount,
    updateOriginalAmount,
    conversionRateInput,
    setConversionRateInput,
    useCustomRate,
    toggleCustomRate: () => setUseCustomRate((value) => !value),
    refreshRate: () => setRateNonce((value) => value + 1),
    saveDefaults,
    setSaveDefaults,
    pending,
    error,
    deleteOpen,
    setDeleteOpen,
    documents,
    pendingFiles,
    handleSubmit,
    handleDelete,
    handleDocuments,
    removeDocument,
    applyExtracted,
    pendingReceiptTotal,
    applyPendingReceiptTotal,
    dismissPendingReceiptTotal,
  }
}
