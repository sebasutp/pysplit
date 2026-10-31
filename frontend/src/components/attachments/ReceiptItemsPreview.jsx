/** Read-only preview of line items returned by receipt AI before saving. */

import { useTranslation } from 'react-i18next'

import { formatCurrency } from '../../utils/currency'

/**
 * @param {{
 *   receipt: {items: any[], total?: number|null, merchant?: string|null}|null,
 *   currency: any,
 *   locale?: string,
 * }} props
 */
export function ReceiptItemsPreview({ receipt, currency, locale = 'en-US' }) {
  const { t } = useTranslation()
  if (!receipt?.items?.length) return null

  return (
    <div className="mt-3 rounded-md border border-border bg-muted/30 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">
          {t('Attachments.extractedItems', 'AI extracted items')}
          {receipt.merchant ? ` · ${receipt.merchant}` : ''}
        </p>
        {receipt.total != null ? (
          <p className="text-sm font-semibold tabular-nums">
            {formatCurrency(currency, receipt.total, locale)}
          </p>
        ) : null}
      </div>
      <ul className="mt-2 flex flex-col divide-y divide-border text-sm">
        {receipt.items.map((item) => (
          <li key={item.id || item.name} className="flex items-center justify-between gap-2 py-1">
            <span className="min-w-0 truncate">{item.name}</span>
            <span className="shrink-0 tabular-nums">
              {formatCurrency(currency, item.amount, locale)}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-muted-foreground">
        {t(
          'Attachments.saveToAssignItems',
          'Save the expense to assign these items to participants.',
        )}
      </p>
    </div>
  )
}
