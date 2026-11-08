/** /groups/:groupId/expenses/:expenseId/items — smart split editor. */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useGroupContext } from '../../components/groups/GroupLayout'
import { ErrorState, LoadingState } from '../../components/common/States'
import { AttachmentList } from '../../components/attachments/AttachmentList'
import { AttachmentPreviewDialog } from '../../components/attachments/AttachmentPreviewDialog'
import { ReceiptFooter } from '../../components/receipts/ReceiptFooter'
import { useFeatures } from '../../hooks/useFeatures'
import { useOnlineStatus } from '../../hooks/useOnlineStatus'
import { useToast } from '../../hooks/useToast'
import { repository } from '../../services/repository'
import { prepareUpload } from '../../utils/attachments'
import { formatCurrency, getCurrencyFromGroup, majorUnits, parseAmount } from '../../utils/currency'
import { getItemDestinations } from '../../utils/domain/receipt-split'
import { Button } from '../../components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../../components/ui/Dialog'
import { FormField } from '../../components/ui/Form'
import { Input } from '../../components/ui/Input'

/**
 * Convert a user-entered quantity in units to integer thousandths.
 *
 * @param {string|number|null|undefined} value
 * @returns {number}
 */
function unitsToMilli(value) {
  const number = Number(String(value ?? '').replace(',', '.'))
  if (!Number.isFinite(number) || number <= 0) return 0
  return Math.round(number * 1000)
}

/**
 * Format integer thousandths as a plain unit string without float artifacts.
 *
 * @param {number} milli
 * @returns {string}
 */
function formatUnits(milli) {
  return String(milli / 1000)
}

/**
 * Build the editable dialog state, prefilled from the item's stored portions.
 *
 * @param {any} item
 * @param {{id: string, name: string}[]} participants
 * @returns {{item: any, quantities: Record<string, string>, shared: string}}
 */
function initialAssignDialog(item, participants) {
  /** @type {Record<string, string>} */
  const quantities = {}
  /** @type {Record<string, number>} */
  const totals = {}
  for (const participant of participants) quantities[participant.id] = ''
  let sharedMilli = 0
  for (const portion of item.portions || []) {
    const milli = Number(portion.quantity_milli) || 0
    if (milli <= 0) continue
    if (portion.target === 'PARTICIPANT') {
      if (portion.participant_id && portion.participant_id in quantities) {
        totals[portion.participant_id] = (totals[portion.participant_id] || 0) + milli
      }
    } else {
      sharedMilli += milli
    }
  }
  for (const [participantId, milli] of Object.entries(totals)) {
    if (milli > 0) quantities[participantId] = formatUnits(milli)
  }
  let shared = sharedMilli > 0 ? formatUnits(sharedMilli) : ''
  // The whole-item flag only applies before any portions exist.
  if ((item.portions || []).length === 0 && item.is_shared) {
    shared = formatUnits(item.quantity_milli)
  }
  return { item, quantities, shared }
}

export function ReceiptItemsPage() {
  const { group } = useGroupContext()
  const { expenseId } = useParams()
  const { t, i18n } = useTranslation()
  const { toast } = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const { features, loading: featuresLoading } = useFeatures()
  const online = useOnlineStatus()
  const locale = i18n.resolvedLanguage || 'en-US'
  const currency = getCurrencyFromGroup(group)
  const participants = group.participants || []

  const [expense, setExpense] = useState(/** @type {any|null} */ (null))
  const [state, setState] = useState(/** @type {any|null} */ (null))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(/** @type {any} */ (null))
  const [uploading, setUploading] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [applying, setApplying] = useState(false)
  const [applyConfirm, setApplyConfirm] = useState(false)

  const [itemDialog, setItemDialog] = useState(
    /** @type {null|{mode: 'add'|'edit', item?: any, name: string, quantity: string, amount: string, shared: boolean}} */ (
      null
    ),
  )
  const [assignDialog, setAssignDialog] = useState(
    /** @type {null|{item: any, quantities: Record<string, string>, shared: string}} */ (null),
  )
  const [deleteItem, setDeleteItem] = useState(/** @type {any|null} */ (null))

  const controllerRef = useRef(/** @type {AbortController|null} */ (null))

  const reload = useCallback(async () => {
    if (!expenseId) return
    // Cancel any previous load so a slow response cannot overwrite a newer one.
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setExpense(null)
    setState(null)
    setError(null)
    setLoading(true)
    try {
      const expensePayload = await repository.expenses.get(group.id, expenseId, {
        signal: controller.signal,
      })
      const receiptAttachment = expensePayload?.attachments?.find(
        (/** @type {any} */ attachment) => attachment.receipt_status,
      )
      const receiptPayload =
        features.receipt_ai && receiptAttachment
          ? await repository.attachments.get(
              group.id,
              { attachment_id: receiptAttachment.id },
              { signal: controller.signal },
            )
          : null
      if (controller.signal.aborted) return
      setExpense(expensePayload)
      setState(receiptPayload)
      setError(null)
    } catch (caught) {
      if (caught && typeof caught === 'object' && /** @type {any} */ (caught).code === 'aborted') {
        return
      }
      if (controller.signal.aborted) return
      setError(caught)
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }, [group.id, expenseId, features.receipt_ai])

  useEffect(() => {
    if (!featuresLoading) void reload()
  }, [featuresLoading, reload])

  // Abort the in-flight request when the page unmounts or the id changes.
  useEffect(
    () => () => {
      controllerRef.current?.abort()
    },
    [],
  )

  const sections = useMemo(() => {
    const participantIds = participants.map((/** @type {any} */ participant) => participant.id)
    /**
     * @type {{key: string, label: string, entries: {item: any, destination: any, showActions: boolean}[]}[]}
     */
    const ordered = [
      {
        key: 'unassigned',
        label: t('ReceiptItems.sections.unassigned', 'Unassigned'),
        entries: [],
      },
      {
        key: 'shared',
        label: t('ReceiptItems.sections.shared', 'Shared'),
        entries: [],
      },
      ...participants.map((/** @type {any} */ participant) => ({
        key: `participant:${participant.id}`,
        label: participant.name,
        entries: /** @type {{item: any, destination: any, showActions: boolean}[]} */ ([]),
      })),
    ]
    const byKey = new Map(ordered.map((section) => [section.key, section]))
    for (const item of state?.items || []) {
      for (const destination of getItemDestinations(item, participantIds)) {
        const key =
          destination.target === 'PARTICIPANT'
            ? `participant:${destination.participantId}`
            : destination.target.toLowerCase()
        const section = byKey.get(key)
        if (!section) continue
        section.entries.push({ item, destination, showActions: false })
      }
    }
    // Whole-item actions appear once, on the first destination in section order.
    const seen = new Set()
    for (const section of ordered) {
      for (const entry of section.entries) {
        if (!seen.has(entry.item.id)) {
          seen.add(entry.item.id)
          entry.showActions = true
        }
      }
    }
    return ordered.filter((section) => section.entries.length)
  }, [state, participants, t])

  /** @param {React.ChangeEvent<HTMLInputElement>} event */
  async function handleUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const prepared = await prepareUpload(file)
      const attachment = await repository.attachments.upload(group.id, prepared.file, {
        width: prepared.width,
        height: prepared.height,
        expense_id: expenseId,
      })
      const result = await repository.attachments.extractItems(group.id, attachment.id, {
        expense_id: expenseId,
      })
      setState(result)
      if (result?.status === 'FAILED' || result?.attachment?.receipt_status === 'FAILED') {
        toast({
          title: t('Attachments.scanError', 'The receipt could not be scanned'),
          description:
            (typeof result.error === 'string' && result.error) ||
            t(
              'ReceiptItems.scanUnavailable',
              'Check the server AI configuration and try again.',
            ),
        })
        return
      }
      toast({
        title: attachment.pending
          ? t('ReceiptItems.scanPending', 'Scan queued')
          : t('ReceiptItems.extracted', 'Receipt scanned'),
        description: attachment.pending
          ? t(
              'ReceiptItems.scanPendingDescription',
              'The image is saved on this device and will be scanned when you are back online.',
            )
          : t('ReceiptItems.extractedDescription', 'Assign the extracted items below.'),
      })
    } catch (caught) {
      toast({
        title: t('ReceiptItems.saveError.title', 'Couldn’t save your change'),
        description:
          caught && typeof caught === 'object' && 'detail' in caught
            ? String(caught.detail)
            : t('ReceiptItems.scanError', 'The receipt could not be scanned.'),
      })
    } finally {
      setUploading(false)
      event.target.value = ''
    }
  }


  /** @param {any} attachment */
  async function scanExistingAttachment(attachment) {
    setUploading(true)
    try {
      const result = await repository.attachments.extractItems(group.id, attachment.id, {
        expense_id: expenseId,
      })
      setState(result)
      if (result?.status === 'FAILED' || result?.attachment?.receipt_status === 'FAILED') {
        toast({
          title: t('Attachments.scanError', 'The receipt could not be scanned'),
          description:
            (typeof result.error === 'string' && result.error) ||
            t(
              'ReceiptItems.scanUnavailable',
              'Check the server AI configuration and try again.',
            ),
        })
        return
      }
      toast({
        title: t('ReceiptItems.extracted', 'Receipt scanned'),
        description: t('ReceiptItems.extractedDescription', 'Assign the extracted items below.'),
      })
    } catch (caught) {
      toast({
        title: t('ReceiptItems.saveError.title', 'Couldn’t save your change'),
        description:
          caught && typeof caught === 'object' && 'detail' in caught
            ? String(caught.detail)
            : t('ReceiptItems.scanError', 'The receipt could not be scanned.'),
      })
    } finally {
      setUploading(false)
    }
  }

  async function saveItem() {
    if (!itemDialog || !state?.attachment) return
    const payload = {
      name: itemDialog.name.trim(),
      quantity_milli: Math.max(1, Math.round(Number(itemDialog.quantity || 1) * 1000)),
      amount: parseAmount(itemDialog.amount, currency.code, locale),
      is_shared: itemDialog.shared,
    }
    try {
      const next =
        itemDialog.mode === 'edit' && itemDialog.item
          ? await repository.attachments.updateItem(
              group.id,
              state.attachment.id,
              itemDialog.item.id,
              payload,
            )
          : await repository.attachments.addItem(group.id, state.attachment.id, payload)
      setState(next)
      setItemDialog(null)
    } catch (caught) {
      toast({
        title: t('ReceiptItems.saveError.title', 'Couldn’t save your change'),
        description: caught instanceof Error ? caught.message : undefined,
      })
    }
  }

  async function assignItem() {
    if (!assignDialog || !state?.attachment) return
    const { item, quantities, shared } = assignDialog
    const portions = []
    for (const participant of participants) {
      const quantityMilli = unitsToMilli(quantities[participant.id] ?? '')
      if (quantityMilli > 0) {
        portions.push({
          target: 'PARTICIPANT',
          participant_id: participant.id,
          quantity_milli: quantityMilli,
        })
      }
    }
    const sharedMilli = unitsToMilli(shared)
    if (sharedMilli > 0) {
      portions.push({ target: 'SHARED', participant_id: null, quantity_milli: sharedMilli })
    }
    if (!portions.length) return
    try {
      const next = await repository.attachments.setPortions(
        group.id,
        state.attachment.id,
        item.id,
        portions,
      )
      setState(next)
      setAssignDialog(null)
    } catch (caught) {
      toast({
        title: t('ReceiptItems.saveError.title', 'Couldn’t save your change'),
        description: caught instanceof Error ? caught.message : undefined,
      })
    }
  }

  async function clearItemPortions() {
    if (!assignDialog || !state?.attachment) return
    try {
      const next = await repository.attachments.setPortions(
        group.id,
        state.attachment.id,
        assignDialog.item.id,
        [],
      )
      setState(next)
      setAssignDialog(null)
    } catch (caught) {
      toast({
        title: t('ReceiptItems.saveError.title', 'Couldn’t save your change'),
        description: caught instanceof Error ? caught.message : undefined,
      })
    }
  }

  /** @param {string} participantId @param {string} value */
  function setAssignQuantity(participantId, value) {
    setAssignDialog((/** @type {any} */ current) =>
      current
        ? { ...current, quantities: { ...current.quantities, [participantId]: value } }
        : current,
    )
  }

  function splitEvenly() {
    setAssignDialog((/** @type {any} */ current) => {
      if (!current) return current
      const total = Number(current.item.quantity_milli) || 0
      const active = participants.filter(
        (/** @type {any} */ participant) =>
          unitsToMilli(current.quantities[participant.id] ?? '') > 0,
      )
      const targets = active.length ? active : participants
      if (!targets.length) return current
      const base = Math.floor(total / targets.length)
      const remainder = total - base * targets.length
      /** @type {Record<string, string>} */
      const quantities = {}
      for (const participant of participants) quantities[participant.id] = ''
      targets.forEach((/** @type {any} */ participant, /** @type {number} */ index) => {
        quantities[participant.id] = formatUnits(base + (index < remainder ? 1 : 0))
      })
      return { ...current, quantities, shared: '' }
    })
  }

  async function removeItem() {
    if (!deleteItem || !state?.attachment) return
    try {
      const next = await repository.attachments.deleteItem(
        group.id,
        state.attachment.id,
        deleteItem.id,
      )
      setState(next)
      setDeleteItem(null)
    } catch (caught) {
      toast({
        title: t('ReceiptItems.saveError.title', 'Couldn’t save your change'),
        description: caught instanceof Error ? caught.message : undefined,
      })
    }
  }

  /** @param {string} participantId @param {boolean} value */
  async function toggleOptOut(participantId, value) {
    if (!state?.attachment) return
    try {
      const next = await repository.attachments.setOptOut(
        group.id,
        state.attachment.id,
        participantId,
        value,
      )
      setState(next)
    } catch (caught) {
      toast({
        title: t('ReceiptItems.saveError.title', 'Couldn’t save your change'),
        description: caught instanceof Error ? caught.message : undefined,
      })
    }
  }

  async function applyReceipt() {
    if (!state?.attachment || !expenseId) return
    setApplying(true)
    try {
      const result = await repository.attachments.apply(group.id, state.attachment.id, {
        expense_id: expenseId,
      })
      setState((/** @type {any} */ previous) => ({
        ...previous,
        attachment: result.attachment,
        split: result.split,
      }))
      setExpense(await repository.expenses.get(group.id, expenseId))
      setApplyConfirm(false)
      toast({
        title: t('ReceiptItems.applySuccess.title', 'Expense updated'),
        description: t(
          'ReceiptItems.applySuccess.description',
          'The receipt items were applied to the expense.',
        ),
      })
      // Return to the screen the user came from (usually the expense form).
      // A direct link has no useful history entry, so fall back to the editor.
      if (location.key && location.key !== 'default') {
        navigate(-1)
      } else {
        navigate(`/groups/${group.id}/expenses/${expenseId}/edit`, { replace: true })
      }
    } catch (caught) {
      toast({
        title: t('ReceiptItems.applyError.title', 'Couldn’t apply the receipt'),
        description: caught instanceof Error ? caught.message : undefined,
      })
    } finally {
      setApplying(false)
    }
  }

  if (loading) return <LoadingState label={t('ReceiptItems.loading', 'Loading receipt…')} />
  if (error) return <ErrorState detail={error.detail || error.message} onRetry={() => void reload()} />
  if (!expense) return <ErrorState title={t('Common.expenseNotFound', 'Expense not found')} />

  if (!features.receipt_ai) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('ReceiptItems.title', 'Receipt items')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm text-muted-foreground">
          <p>
            {t(
              'ReceiptItems.disabled',
              'Smart split is not enabled on this server. Receipt scanning is an online-only feature.',
            )}
          </p>
          <Link className="text-primary underline" to={`/groups/${group.id}/expenses/${expenseId}/edit`}>
            {t('ReceiptItems.backToExpense', 'Back to expense')}
          </Link>
        </CardContent>
      </Card>
    )
  }

  if (!state) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('ReceiptItems.title', 'Receipt items')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            {t('ReceiptItems.noReceipt', 'No receipt is linked to this expense yet.')}
          </p>
          {expense.attachments?.length ? (
            <AttachmentList
              attachments={expense.attachments}
              canScan={Boolean(features.receipt_ai)}
              scanningId={uploading ? 'scanning' : null}
              onScan={scanExistingAttachment}
            />
          ) : null}
          {!online ? (
            <p role="status" className="text-sm text-muted-foreground">
              {t(
                'ReceiptItems.offlineQueue',
                'You are offline. Attach the photo now and it will be scanned after you reconnect.',
              )}
            </p>
          ) : null}
          <input
            type="file"
            accept="image/*,application/pdf"
            disabled={uploading}
            onChange={handleUpload}
            aria-label={t('ReceiptItems.upload', 'Upload a receipt photo')}
          />
          {uploading ? <LoadingState label={t('ReceiptItems.scanning', 'Scanning receipt…')} /> : null}
          <Link className="text-sm text-primary underline" to={`/groups/${group.id}/expenses/${expenseId}/edit`}>
            {t('ReceiptItems.backToExpense', 'Back to expense')}
          </Link>
        </CardContent>
      </Card>
    )
  }

  const split = state.split
  const diverged = expense.amount !== (split?.items_total ?? expense.amount)
  const receipt = state.attachment
  const assignedMilli = assignDialog
    ? Object.values(assignDialog.quantities).reduce(
        (/** @type {number} */ sum, /** @type {string} */ value) => sum + unitsToMilli(value),
        0,
      ) + unitsToMilli(assignDialog.shared)
    : 0
  const exceeds = assignDialog ? assignedMilli > assignDialog.item.quantity_milli : false

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          {receipt.content_type?.startsWith('image/') && !String(receipt.url).startsWith('local-') ? (
            <button
              type="button"
              className="h-20 w-20 overflow-hidden rounded border border-border"
              onClick={() => setPreviewOpen(true)}
              aria-label={t('Attachments.preview', 'Preview')}
            >
              <img
                src={receipt.thumbnail_url || receipt.url}
                alt=""
                className="h-full w-full object-cover"
              />
            </button>
          ) : null}
          <div>
            <h2 className="text-xl font-semibold">{t('ReceiptItems.title', 'Receipt items')}</h2>
            <p className="text-sm text-muted-foreground">
              {receipt.merchant || t('ReceiptItems.merchant', 'Merchant')} ·{' '}
              {receipt.receipt_status}
            </p>
          </div>
          {receipt.pending_scan || receipt.pending ? (
            <p
              data-testid="receipt-scan-pending"
              className="mt-1 text-xs font-medium text-amber-600 dark:text-amber-400"
            >
              {t('ReceiptItems.scanPending', 'Scan queued')}
            </p>
          ) : null}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() =>
              setItemDialog({ mode: 'add', name: '', quantity: '1', amount: '', shared: false })
            }
          >
            {t('ReceiptItems.addItem', 'Add item')}
          </Button>
          <Link className="self-center text-sm text-primary underline" to={`/groups/${group.id}/expenses/${expenseId}/edit`}>
            {t('ReceiptItems.backToExpense', 'Back to expense')}
          </Link>
        </div>
      </div>

      {receipt.total !== null && receipt.total !== undefined ? (
        <p className="text-sm">
          {t('ReceiptItems.printedTotal', 'Printed total')}:{' '}
          <span className="font-semibold">{formatCurrency(currency, receipt.total, locale)}</span>
        </p>
      ) : null}

      {state.items?.length ? (
        <div className="flex flex-col gap-4">
          {sections.map((section) => (
            <Card key={section.key}>
              <CardHeader>
                <CardTitle className="text-base">
                  {section.label}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col divide-y divide-border">
                  {section.entries.map((/** @type {{item: any, destination: any, showActions: boolean}} */ entry) => {
                    const { item, destination, showActions } = entry
                    const quantityContext =
                      destination.target === 'UNASSIGNED'
                        ? `${section.label}, ${formatUnits(destination.quantityMilli)} left`
                        : `${section.label}, ${formatUnits(destination.quantityMilli)} of ${formatUnits(item.quantity_milli)}`
                    const itemNumber = Number(item.position)
                    const itemSuffix = Number.isFinite(itemNumber)
                      ? ` (item ${itemNumber + 1})`
                      : ''
                    return (
                    <li
                      key={`${item.id}:${section.key}`}
                      className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                    >
                      <div>
                        <p className="font-medium">{item.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {destination.target === 'UNASSIGNED'
                            ? t('ReceiptItems.item.remaining', '{{quantity}} left', {
                                quantity: formatUnits(destination.quantityMilli),
                              })
                            : t('ReceiptItems.item.quantity', '{{assigned}} of {{total}}', {
                                assigned: formatUnits(destination.quantityMilli),
                                total: formatUnits(item.quantity_milli),
                              })}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold tabular-nums">
                          {formatCurrency(currency, destination.amount, locale)}
                        </span>
                        {showActions ? (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              aria-label={`${t('ReceiptItems.item.assign', 'Assign')} ${item.name} for ${quantityContext}${itemSuffix}`}
                              onClick={() =>
                                setAssignDialog(initialAssignDialog(item, participants))
                              }
                            >
                              {t('ReceiptItems.item.assign', 'Assign')}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={`${t('ReceiptItems.item.edit', 'Edit')} ${item.name} for ${quantityContext}${itemSuffix}`}
                              onClick={() =>
                                setItemDialog({
                                  mode: 'edit',
                                  item,
                                  name: item.name,
                                  quantity: String(item.quantity_milli / 1000),
                                  amount: majorUnits(item.amount, currency.code),
                                  shared: item.is_shared,
                                })
                              }
                            >
                              {t('ReceiptItems.item.edit', 'Edit')}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive"
                              aria-label={`${t('ReceiptItems.item.delete', 'Delete')} ${item.name} for ${quantityContext}${itemSuffix}`}
                              onClick={() => setDeleteItem(item)}
                            >
                              {t('ReceiptItems.item.delete', 'Delete')}
                            </Button>
                          </>
                        ) : null}
                      </div>
                    </li>
                    )
                  })}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          {t('ReceiptItems.empty', 'No items yet. Add one to start splitting.')}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('ReceiptItems.optOutTitle', 'Opt-outs')}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col gap-2 text-sm">
            {participants.map((/** @type {any} */ participant) => {
              const optedOut = (state.opt_outs || []).includes(participant.id)
              return (
                <li key={participant.id}>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={optedOut}
                      onChange={(event) => void toggleOptOut(participant.id, event.target.checked)}
                    />
                    <span>
                      {participant.name} · {t('ReceiptItems.footer.optOut', 'Shares unassigned items')}
                    </span>
                  </label>
                </li>
              )
            })}
          </ul>
        </CardContent>
      </Card>

      <ReceiptFooter
        split={split}
        currency={currency}
        participants={participants}
        applying={applying}
        diverged={diverged}
        onApply={() => {
          if (diverged) setApplyConfirm(true)
          else void applyReceipt()
        }}
      />

      <Dialog open={Boolean(itemDialog)} onOpenChange={(open) => !open && setItemDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {itemDialog?.mode === 'edit'
                ? t('ReceiptItems.item.editTitle', 'Edit item')
                : t('ReceiptItems.AddItemDialog.title', 'Add item')}
            </DialogTitle>
          </DialogHeader>
          {itemDialog ? (
            <div className="mt-3 flex flex-col gap-3">
              <FormField label={t('ReceiptItems.AddItemDialog.nameLabel', 'Name')} htmlFor="item-name">
                <Input
                  id="item-name"
                  value={itemDialog.name}
                  onChange={(event) =>
                    setItemDialog({ ...itemDialog, name: event.target.value })
                  }
                />
              </FormField>
              <FormField label={t('ReceiptItems.AddItemDialog.quantityLabel', 'Quantity')} htmlFor="item-quantity">
                <Input
                  id="item-quantity"
                  inputMode="decimal"
                  value={itemDialog.quantity}
                  onChange={(event) =>
                    setItemDialog({ ...itemDialog, quantity: event.target.value })
                  }
                />
              </FormField>
              <FormField label={t('ReceiptItems.AddItemDialog.amountLabel', 'Amount')} htmlFor="item-amount">
                <Input
                  id="item-amount"
                  inputMode="decimal"
                  value={itemDialog.amount}
                  onChange={(event) =>
                    setItemDialog({ ...itemDialog, amount: event.target.value })
                  }
                />
              </FormField>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={itemDialog.shared}
                  onChange={(event) =>
                    setItemDialog({ ...itemDialog, shared: event.target.checked })
                  }
                />
                {t('ReceiptItems.AddItemDialog.sharedLabel', 'Shared (whole-bill charge)')}
              </label>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setItemDialog(null)}>
                  {t('ReceiptItems.AddItemDialog.cancel', 'Cancel')}
                </Button>
                <Button onClick={() => void saveItem()}>
                  {itemDialog.mode === 'edit'
                    ? t('ReceiptItems.item.save', 'Save')
                    : t('ReceiptItems.AddItemDialog.add', 'Add')}
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(assignDialog)} onOpenChange={(open) => !open && setAssignDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('ReceiptItems.assign.title', 'Assign item')}</DialogTitle>
            <DialogDescription>
              {t('ReceiptItems.assign.description', 'Choose who pays for “{{name}}”.', {
                name: assignDialog?.item?.name || '',
              })}
            </DialogDescription>
          </DialogHeader>
          {assignDialog ? (
            <div className="mt-3 flex flex-col gap-3">
              <p className="text-sm font-medium">
                {t('ReceiptItems.assign.custom', 'Custom split')}
              </p>
              <p className="text-xs text-muted-foreground">
                {t(
                  'ReceiptItems.assign.customHint',
                  'Enter quantities in units for each target.',
                )}
              </p>
              {participants.map((/** @type {any} */ participant) => (
                <label
                  key={participant.id}
                  className="flex items-center justify-between gap-3 text-sm"
                >
                  <span>{participant.name}</span>
                  <Input
                    aria-label={participant.name}
                    className="w-24"
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="any"
                    value={assignDialog.quantities[participant.id] ?? ''}
                    onChange={(event) => setAssignQuantity(participant.id, event.target.value)}
                  />
                </label>
              ))}
              <label className="flex items-center justify-between gap-3 text-sm">
                <span>{t('ReceiptItems.assign.shared', 'Shared')}</span>
                <Input
                  aria-label={t('ReceiptItems.assign.shared', 'Shared')}
                  className="w-24"
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="any"
                  value={assignDialog.shared}
                  onChange={(event) =>
                    setAssignDialog({ ...assignDialog, shared: event.target.value })
                  }
                />
              </label>
              <p className="text-sm" data-testid="assign-summary">
                {t('ReceiptItems.item.quantity', '{{assigned}} of {{total}}', {
                  assigned: formatUnits(assignedMilli),
                  total: formatUnits(assignDialog.item.quantity_milli),
                })}
              </p>
              {exceeds ? (
                <p role="alert" className="text-sm text-destructive">
                  {t(
                    'ReceiptItems.assign.exceeds',
                    'The assigned quantity exceeds the item quantity.',
                  )}
                </p>
              ) : null}
              <div className="flex flex-wrap justify-end gap-2">
                {assignDialog.item.portions?.length || assignDialog.item.is_shared ? (
                  <Button
                    variant="ghost"
                    className="text-destructive"
                    onClick={() => void clearItemPortions()}
                  >
                    {t('ReceiptItems.item.removePortion', 'Remove portion')}
                  </Button>
                ) : null}
                <Button variant="outline" onClick={splitEvenly}>
                  {t('ReceiptItems.assign.even', 'Split evenly')}
                </Button>
                <Button variant="ghost" onClick={() => setAssignDialog(null)}>
                  {t('ReceiptItems.assign.cancel', 'Cancel')}
                </Button>
                <Button
                  onClick={() => void assignItem()}
                  disabled={assignedMilli <= 0 || exceeds}
                >
                  {t('ReceiptItems.assign.confirm', 'Assign')}
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deleteItem)} onOpenChange={(open) => !open && setDeleteItem(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('ReceiptItems.item.deleteConfirm', 'Delete this item?')}</DialogTitle>
            <DialogDescription>
              {t('ReceiptItems.item.deleteDescription', 'This removes the item and its assignments.')}
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleteItem(null)}>
              {t('ReceiptItems.item.cancel', 'Cancel')}
            </Button>
            <Button variant="destructive" onClick={() => void removeItem()}>
              {t('ReceiptItems.item.delete', 'Delete')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={applyConfirm} onOpenChange={setApplyConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('ReceiptItems.applyConfirm.title', 'Update the expense?')}</DialogTitle>
            <DialogDescription>
              {t(
                'ReceiptItems.applyConfirm.description',
                'The expense total differs from the receipt items total. Applying will overwrite the expense amount and its split.',
              )}
            </DialogDescription>
          </DialogHeader>
          <p className="mt-2 text-sm">
            {t('ReceiptItems.applyConfirm.total', 'total {{current}} → {{new}}', {
              current: formatCurrency(currency, expense.amount, locale),
              new: formatCurrency(currency, split?.items_total || 0, locale),
            })}
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setApplyConfirm(false)}>
              {t('ReceiptItems.applyConfirm.cancel', 'Cancel')}
            </Button>
            <Button onClick={() => void applyReceipt()} disabled={applying}>
              {t('ReceiptItems.applyConfirm.confirm', 'Apply')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      <AttachmentPreviewDialog
        attachment={receipt}
        open={previewOpen}
        onOpenChange={setPreviewOpen}
      />
    </section>
  )
}

