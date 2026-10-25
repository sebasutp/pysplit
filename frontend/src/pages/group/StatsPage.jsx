/** /groups/:groupId/stats */

import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useGroupContext } from '../../components/groups/GroupLayout'
import { ErrorState, LoadingState } from '../../components/common/States'
import { useActiveUser } from '../../hooks/useActiveUser'
import { useDrilldown, useStats } from '../../hooks/useStats'
import { formatCurrency, getCurrencyFromGroup } from '../../utils/currency'
import { STATS_RANGES, monthLabel, resolveRange } from '../../utils/stats-range'
import { Button } from '../../components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/Card'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../../components/ui/Dialog'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'

export function StatsPage() {
  const { group } = useGroupContext()
  const { activeUserId } = useActiveUser(group.id)
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage || 'en-US'
  const currency = getCurrencyFromGroup(group)
  const [preset, setPreset] = useState('all')
  const [custom, setCustom] = useState({ from: '', to: '' })
  const [drilldown, setDrilldown] = useState(
    /** @type {null|{kind: 'category', categoryId: number, label: string}|{kind: 'month', month: string, label: string}} */ (
      null
    ),
  )
  const range = useMemo(() => resolveRange(preset, custom), [preset, custom])
  const { stats, loading, error, reload } = useStats(group.id, {
    participantId: activeUserId,
    from: range.from,
    to: range.to,
  })

  const drilldownTarget = useMemo(
    () =>
      drilldown?.kind === 'category'
        ? { kind: /** @type {const} */ ('category'), categoryId: drilldown.categoryId }
        : drilldown?.kind === 'month'
          ? { kind: /** @type {const} */ ('month'), month: drilldown.month }
          : { kind: /** @type {const} */ ('month'), month: '1970-01' },
    [drilldown],
  )
  const drill = useDrilldown(group.id, drilldownTarget, range)

  if (loading && !stats) return <LoadingState label={t('Stats.loading', 'Loading statistics…')} />
  if (error) return <ErrorState detail={error.detail || error.message} onRetry={reload} />
  if (!stats) return null

  const summary = stats.summary || {}
  const largest = summary.largestExpense || summary.largest_expense
  const totalGroup = stats.total_group_spending ?? stats.totalGroupSpendings ?? 0
  const personalPaid = stats.total_active_user_paid_for ?? stats.totalParticipantSpendings
  const personalShare = stats.total_active_user_share ?? stats.totalParticipantShare
  const months = stats.spending_over_time || stats.months || []
  const participants = stats.spending_by_participant || stats.participants || []
  const categories = stats.spending_by_category || stats.categories || []
  const recurring = stats.recurring || {}

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">{t('Stats.title', 'Stats')}</h2>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-44">
            <Select
              value={preset}
              options={STATS_RANGES.map((item) => ({
                value: item.value,
                label: t(`Stats.range.${item.value}`, item.label),
              }))}
              onChange={setPreset}
            />
          </div>
          {preset === 'custom' ? (
            <>
              <label className="flex flex-col gap-1 text-xs font-medium">
                {t('Stats.range.from', 'From')}
                <Input
                  type="date"
                  value={custom.from}
                  onChange={(event) =>
                    setCustom((previous) => ({ ...previous, from: event.target.value }))
                  }
                />
              </label>
              <label className="flex flex-col gap-1 text-xs font-medium">
                {t('Stats.range.to', 'To')}
                <Input
                  type="date"
                  value={custom.to}
                  onChange={(event) =>
                    setCustom((previous) => ({ ...previous, to: event.target.value }))
                  }
                />
              </label>
            </>
          ) : null}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('Stats.Totals.title', 'Totals')}</CardTitle>
          <CardDescription>
            {t('Stats.Totals.description', 'Spending summary of the entire group.')}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span>{t('Stats.Totals.groupSpendings', 'Total group spendings')}</span>
            <span className="font-semibold tabular-nums">
              {formatCurrency(currency, totalGroup, locale)}
            </span>
          </div>
          {activeUserId && personalPaid !== null && personalPaid !== undefined ? (
            <div className="flex items-center justify-between gap-2">
              <span>{t('Stats.Totals.yourSpendings', 'Your total spendings')}</span>
              <span className="font-semibold tabular-nums">
                {formatCurrency(currency, personalPaid, locale)}
              </span>
            </div>
          ) : null}
          {activeUserId && personalShare !== null && personalShare !== undefined ? (
            <div className="flex items-center justify-between gap-2">
              <span>{t('Stats.Totals.yourShare', 'Your total share')}</span>
              <span className="font-semibold tabular-nums">
                {formatCurrency(currency, personalShare, locale)}
              </span>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('Stats.Summary.title', 'Summary')}</CardTitle>
          <CardDescription>
            {t('Stats.Summary.description', 'Key figures for the selected period.')}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <div className="flex items-center justify-between gap-2">
            <span>{t('Stats.Summary.expenseCount', 'Expenses')}</span>
            <span className="font-semibold tabular-nums">{summary.expenseCount ?? 0}</span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span>{t('Stats.Summary.averageExpense', 'Average expense')}</span>
            <span className="font-semibold tabular-nums">
              {formatCurrency(currency, summary.averageExpense ?? 0, locale)}
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span>{t('Stats.Summary.largestExpense', 'Largest expense')}</span>
            <span className="font-semibold tabular-nums">
              {formatCurrency(currency, largest?.amount ?? 0, locale)}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('Stats.OverTime.title', 'Spending over time')}</CardTitle>
          <CardDescription>
            {t(
              'Stats.OverTime.description',
              'Total group spending per month. Select a month to see its expenses.',
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {months.length ? (
            <ul className="flex flex-col gap-1 text-sm">
              {months.map((/** @type {any} */ row) => (
                <li key={row.month} className="flex items-center justify-between gap-2">
                  <Button
                    variant="link"
                    size="sm"
                    aria-label={t('Stats.OverTime.showExpensesPlain', 'Show expenses for {{month}}', {
                      month: monthLabel(row.month, locale),
                    })}
                    onClick={() =>
                      setDrilldown({
                        kind: 'month',
                        month: row.month,
                        label: monthLabel(row.month, locale),
                      })
                    }
                  >
                    {monthLabel(row.month, locale)}
                  </Button>
                  <span className="tabular-nums">
                    {formatCurrency(currency, row.total, locale)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t('Stats.OverTime.empty', 'There are no expenses yet.')}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('Stats.ByParticipant.title', 'Spending by participant')}</CardTitle>
          <CardDescription>
            {t(
              'Stats.ByParticipant.description',
              'How much each participant paid and their share of the expenses.',
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {participants.length ? (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-xs uppercase text-muted-foreground">
                  <th className="py-1">{t('Stats.ByParticipant.participant', 'Participant')}</th>
                  <th className="py-1 text-right">{t('Stats.ByParticipant.paid', 'Paid')}</th>
                  <th className="py-1 text-right">{t('Stats.ByParticipant.share', 'Share')}</th>
                </tr>
              </thead>
              <tbody>
                {participants.map((/** @type {any} */ row) => (
                  <tr key={row.participant_id || row.participantId} className="border-t border-border">
                    <td className="py-1.5">{row.name}</td>
                    <td className="py-1.5 text-right tabular-nums">
                      {formatCurrency(currency, row.paid ?? row.amount ?? 0, locale)}
                    </td>
                    <td className="py-1.5 text-right tabular-nums">
                      {formatCurrency(currency, row.share ?? 0, locale)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t('Stats.ByParticipant.empty', 'There are no expenses yet.')}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('Stats.ByCategory.title', 'Spending by category')}</CardTitle>
          <CardDescription>
            {t(
              'Stats.ByCategory.description',
              'Total amount spent in each category. Select a category to see its expenses.',
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {categories.length ? (
            <ul className="flex flex-col gap-1 text-sm">
              {categories.map((/** @type {any} */ row) => (
                <li key={row.category_id ?? row.categoryId} className="flex items-center justify-between gap-2">
                  <Button
                    variant="link"
                    size="sm"
                    aria-label={t('Stats.ByCategory.showExpensesPlain', 'Show expenses for {{category}}', {
                      category: row.name,
                    })}
                    onClick={() =>
                      setDrilldown({
                        kind: 'category',
                        categoryId: row.category_id ?? row.categoryId,
                        label: row.name,
                      })
                    }
                  >
                    {row.name}
                  </Button>
                  <span className="tabular-nums">
                    {formatCurrency(currency, row.amount ?? row.total ?? 0, locale)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t('Stats.ByCategory.empty', 'There are no expenses yet.')}
            </p>
          )}
        </CardContent>
      </Card>

      {recurring.count ? (
        <Card>
          <CardHeader>
            <CardTitle>{t('Stats.Recurring.title', 'Recurring expenses')}</CardTitle>
            <CardDescription>
              {t(
                'Stats.Recurring.description',
                "Estimated cost of the group's active recurring expenses.",
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              {t('Stats.Recurring.estimatedMonthly', 'Estimated monthly cost')}:{' '}
              <span className="font-semibold">
                {formatCurrency(currency, recurring.estimated_monthly ?? 0, locale)}
              </span>
            </p>
          </CardContent>
        </Card>
      ) : null}

      <Dialog open={Boolean(drilldown)} onOpenChange={(open) => !open && setDrilldown(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{drilldown?.label}</DialogTitle>
            <DialogDescription>
              {drilldown?.kind === 'category'
                ? t(
                    'Stats.ByCategory.detailsDescription',
                    'Expenses in this category for the selected period.',
                  )
                : t(
                    'Stats.OverTime.detailsDescription',
                    'Expenses in this month for the selected period.',
                  )}
            </DialogDescription>
          </DialogHeader>
          {drill.loading ? (
            <LoadingState />
          ) : drill.expenses.length ? (
            <ul className="mt-3 flex flex-col divide-y divide-border text-sm">
              {drill.expenses.map((/** @type {any} */ expense) => (
                <li key={expense.id} className="flex items-center justify-between gap-2 py-1.5">
                  <span>{expense.title}</span>
                  <span className="tabular-nums">
                    {formatCurrency(currency, expense.amount, locale)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-muted-foreground">
              {t('Stats.OverTime.detailsEmpty', 'There are no expenses in this month.')}
            </p>
          )}
        </DialogContent>
      </Dialog>
    </section>
  )
}
