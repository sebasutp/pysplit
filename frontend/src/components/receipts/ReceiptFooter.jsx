/** Provisional totals and the apply action for a receipt. */

import { useTranslation } from 'react-i18next'

import { formatCurrency } from '../../utils/currency'
import { Button } from '../ui/Button'

/**
 * @param {{
 *   split: any,
 *   currency: {code: string, symbol: string},
 *   participants: {id: string, name: string}[],
 *   onApply: () => void,
 *   applying?: boolean,
 *   diverged?: boolean,
 * }} props
 */
export function ReceiptFooter({
  split,
  currency,
  participants,
  onApply,
  applying = false,
  diverged = false,
}) {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage || 'en-US'
  const totals = split?.participants || []
  const total = split?.items_total ?? 0
  const assigned = totals.reduce(
    (/** @type {number} */ sum, /** @type {any} */ row) => sum + Number(row.total || 0),
    0,
  )
  const offBy = assigned - total

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="font-semibold">{t('ReceiptItems.footer.itemsTotal', 'Items total')}</h3>
      <ul className="mt-2 flex flex-col gap-1 text-sm">
        {participants.map((participant) => {
          const row = /** @type {any[]} */ (totals).find(
            (/** @type {any} */ item) => item.participant_id === participant.id,
          )
          return (
            <li key={participant.id} className="flex items-center justify-between gap-2">
              <span>{participant.name}</span>
              <span className="tabular-nums">
                {formatCurrency(currency, row?.total || 0, locale)}
              </span>
            </li>
          )
        })}
      </ul>
      <dl className="mt-3 flex flex-col gap-1 border-t border-border pt-3 text-sm">
        <div className="flex items-center justify-between gap-2">
          <dt>{t('ReceiptItems.footer.itemsTotal', 'Items total')}</dt>
          <dd className="tabular-nums">{formatCurrency(currency, total, locale)}</dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt>{t('ReceiptItems.footer.unassigned', 'Unassigned')}</dt>
          <dd className="tabular-nums">
            {formatCurrency(currency, split?.unassigned_pool || 0, locale)}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt>{t('ReceiptItems.footer.shared', 'Shared')}</dt>
          <dd className="tabular-nums">
            {formatCurrency(currency, split?.shared_pool || 0, locale)}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-2">
          <dt>{t('ReceiptItems.footer.reconciles', 'Reconciles')}</dt>
          <dd className="tabular-nums">
            {offBy === 0
              ? formatCurrency(currency, 0, locale)
              : t('ReceiptItems.footer.offBy', 'Off by {{amount}}', {
                  amount: formatCurrency(currency, offBy, locale),
                })}
          </dd>
        </div>
      </dl>
      {split?.all_opted_out ? (
        <p className="mt-2 text-xs text-destructive">
          {t(
            'ReceiptItems.footer.allOptedOut',
            'Everyone opted out, but some items are still unassigned.',
          )}
        </p>
      ) : null}
      <Button className="mt-3 w-full" onClick={onApply} disabled={applying}>
        {diverged
          ? t('ReceiptItems.footer.divergent', 'Receipt values differ · Apply again')
          : t('ReceiptItems.footer.apply', 'Apply to expense')}
      </Button>
    </div>
  )
}
