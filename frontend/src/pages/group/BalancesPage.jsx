/** /groups/:groupId/balances */

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useGroupContext } from '../../components/groups/GroupLayout'
import { ErrorState, LoadingState } from '../../components/common/States'
import { useBalances } from '../../hooks/useBalances'
import { formatCurrency, getCurrencyFromGroup } from '../../utils/currency'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/Card'

export function BalancesPage() {
  const { group } = useGroupContext()
  const { t, i18n } = useTranslation()
  const { balances, reimbursements, loading, error, reload } = useBalances(group.id)
  const currency = getCurrencyFromGroup(group)
  const locale = i18n.resolvedLanguage || 'en-US'
  const participants = group.participants || []
  const nameOf = (/** @type {string} */ id) =>
    participants.find((/** @type {any} */ participant) => participant.id === id)?.name || id

  if (loading) return <LoadingState label={t('Balances.loading', 'Loading balances…')} />
  if (error) return <ErrorState detail={error.detail || error.message} onRetry={reload} />

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-xl font-semibold">{t('Balances.title', 'Balances')}</h2>
        <p className="text-sm text-muted-foreground">
          {t(
            'Balances.description',
            'This is the amount that each participant paid or was paid for.',
          )}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('Balances.title', 'Balances')}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col divide-y divide-border">
            {participants.map((/** @type {any} */ participant) => {
              const value =
                balances.find(
                  (/** @type {any} */ entry) => entry.participant_id === participant.id,
                )?.total || 0
              return (
                <li
                  key={participant.id}
                  data-testid="balance-row"
                  data-participant={participant.name}
                  className="flex items-center justify-between gap-3 py-2 text-sm"
                >
                  <span>{participant.name}</span>
                  <span
                    className={`font-semibold tabular-nums ${
                      value > 0 ? 'text-green-600' : value < 0 ? 'text-red-600' : ''
                    }`}
                  >
                    {formatCurrency(currency, value, locale)}
                  </span>
                </li>
              )
            })}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('Balances.Reimbursements.title', 'Suggested reimbursements')}</CardTitle>
          <CardDescription>
            {t(
              'Balances.Reimbursements.description',
              'Here are suggestions for optimized reimbursements between participants.',
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {reimbursements.length ? (
            <ul className="flex flex-col divide-y divide-border">
              {reimbursements.map((/** @type {any} */ row) => {
                const query = new URLSearchParams({
                  reimbursement: 'yes',
                  from: row.from,
                  to: row.to,
                  amount: String(row.amount),
                })
                return (
                  <li
                    key={`${row.from}-${row.to}`}
                    data-testid="reimbursement-row"
                    data-from={nameOf(row.from)}
                    data-to={nameOf(row.to)}
                    className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                  >
                    <span>
                      {t('Balances.Reimbursements.owesPlain', '{{from}} owes {{to}}', {
                        from: nameOf(row.from),
                        to: nameOf(row.to),
                      })}
                    </span>
                    <span className="flex items-center gap-3">
                      <span className="font-semibold tabular-nums">
                        {formatCurrency(currency, row.amount, locale)}
                      </span>
                      <Link
                        to={`/groups/${group.id}/expenses/create?${query.toString()}`}
                        className="text-primary underline underline-offset-4"
                      >
                        {t('Balances.Reimbursements.markAsPaid', 'Mark as paid')}
                      </Link>
                    </span>
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t(
                'Balances.Reimbursements.noImbursements',
                'It looks like your group doesn’t need any reimbursement 😁',
              )}
            </p>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
