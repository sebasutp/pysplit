/** Aggregated balance across every group with an active user. */

import { useTranslation } from 'react-i18next'

import { useGlobalBalance } from '../../hooks/useGlobalBalance'
import { formatCurrency, getCurrencyFromGroup } from '../../utils/currency'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/Card'
import { Skeleton } from '../ui/Feedback'

/**
 * @param {{groups: {id: string, name: string}[]}} props
 */
export function GlobalBalanceCard({ groups }) {
  const { t, i18n } = useTranslation()
  const { entries, balances, loading } = useGlobalBalance(groups)

  // Wait until localStorage has been read; hide entirely when the user has not
  // identified themselves in any group.
  if (entries === null || entries.length === 0) return null

  /** @type {Map<string, {currency: any, amount: number}>} */
  const byCurrency = new Map()
  for (const balance of balances) {
    const currency = getCurrencyFromGroup(balance)
    const key = currency.code || `custom:${currency.symbol}`
    const existing = byCurrency.get(key)
    if (existing) existing.amount += balance.amount
    else byCurrency.set(key, { currency, amount: balance.amount })
  }
  const currencyBalances = [...byCurrency.values()]
  const settled = !loading && currencyBalances.every(({ amount }) => amount === 0)

  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle>{t('Groups.GlobalBalance.title', 'Your total balance')}</CardTitle>
        <CardDescription>
          {t('Groups.GlobalBalance.description', 'Your combined balance across all your groups.')}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-6 w-40" />
        ) : settled ? (
          <p className="text-sm text-muted-foreground">
            {t(
              'Groups.GlobalBalance.settledUp',
              'You are all settled up across your groups.',
            )}
          </p>
        ) : (
          <ul className="flex flex-col gap-1">
            {currencyBalances.map(({ currency, amount }) => {
              if (amount === 0) return null
              return (
                <li
                  key={currency.code || currency.symbol}
                  className="flex items-baseline justify-between gap-2 text-sm"
                >
                  <span className="text-muted-foreground">
                    {amount > 0
                      ? t('Groups.GlobalBalance.owedToYou', 'You are owed')
                      : t('Groups.GlobalBalance.youOwe', 'You owe')}
                  </span>
                  <span
                    className={`font-semibold tabular-nums ${
                      amount > 0 ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    {formatCurrency(currency, Math.abs(amount), i18n.resolvedLanguage)}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
