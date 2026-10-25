/** Expense list with search, date groups and exports. */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useCategories } from '../../hooks/useCategories'
import { useExpenses } from '../../hooks/useExpenses'
import { useToast } from '../../hooks/useToast'
import { repository } from '../../services/repository'
import { groupExpensesByDate } from '../../utils/date-groups'
import { EmptyState, ErrorState, LoadingState } from '../common/States'
import { buttonVariants } from '../ui/Button'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { ExpenseCard } from './ExpenseCard'

/**
 * @param {{
 *   group: any,
 *   activeUserId: string|null,
 * }} props
 */
export function ExpenseList({ group, activeUserId }) {
  const { t, i18n } = useTranslation()
  const { toast } = useToast()
  const [query, setQuery] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const { items, total, loading, error, reload } = useExpenses(group.id, {
    q: query,
    from: from || null,
    to: to || null,
  })
  const { categories } = useCategories()
  const groups = useMemo(
    () => groupExpensesByDate(items, i18n.resolvedLanguage || 'en-US'),
    [items, i18n.resolvedLanguage],
  )

  /** @param {'csv'|'json'} kind */
  async function exportExpenses(kind) {
    try {
      const file =
        kind === 'csv'
          ? await repository.exports.csv(group.id)
          : await repository.exports.json(group.id)
      const blob = new Blob([file.content], {
        type: kind === 'csv' ? 'text/csv' : 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = file.filename
      anchor.click()
      URL.revokeObjectURL(url)
    } catch (caught) {
      toast({
        title: t('Expenses.exportError', 'Could not export the expenses'),
        description: caught instanceof Error ? caught.message : undefined,
      })
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-xl font-semibold">{t('Expenses.title', 'Expenses')}</h2>
          <p className="text-sm text-muted-foreground">
            {t('Expenses.description', 'Here are the expenses that you created for your group.')}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <details className="relative">
            <summary className={`${buttonVariants({ variant: 'outline', size: 'sm' })} cursor-pointer list-none`}>
              {t('Expenses.export', 'Export')}
            </summary>
            <div className="absolute right-0 z-30 mt-1 w-44 rounded-md border border-border bg-popover p-1 text-sm shadow-lg">
              <button
                type="button"
                className="block w-full rounded px-2 py-1.5 text-left hover:bg-accent"
                onClick={() => void exportExpenses('csv')}
              >
                {t('Expenses.exportCsv', 'Export to CSV')}
              </button>
              <button
                type="button"
                className="block w-full rounded px-2 py-1.5 text-left hover:bg-accent"
                onClick={() => void exportExpenses('json')}
              >
                {t('Expenses.exportJson', 'Export to JSON')}
              </button>
            </div>
          </details>
          <Link
            to={`/groups/${group.id}/expenses/create`}
            className={buttonVariants({ variant: 'default' })}
          >
            {t('Expenses.create', 'Create expense')}
          </Link>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-48 flex-1">
          <Input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('Expenses.searchPlaceholder', 'Search for an expense…')}
            aria-label={t('Expenses.search', 'Search expenses')}
          />
        </div>
        <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
          {t('Expenses.filterFrom', 'From')}
          <Input type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
          {t('Expenses.filterTo', 'To')}
          <Input type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        </label>
        {query || from || to ? (
          <Button
            variant="ghost"
            onClick={() => {
              setQuery('')
              setFrom('')
              setTo('')
            }}
          >
            {t('Expenses.clearSearch', 'Clear')}
          </Button>
        ) : null}
      </div>

      {error ? (
        <ErrorState detail={error.detail || error.message} onRetry={reload} />
      ) : loading && !items.length ? (
        <LoadingState label={t('Expenses.loading', 'Loading expenses…')} />
      ) : !items.length ? (
        <EmptyState
          title={t('Expenses.noExpenses', 'Your group doesn’t contain any expense yet.')}
          action={
            <Link
              to={`/groups/${group.id}/expenses/create`}
              className={buttonVariants({ variant: 'default' })}
            >
              {t('Expenses.createFirst', 'Create the first one')}
            </Link>
          }
        />
      ) : (
        <div className="flex flex-col gap-5">
          {groups.map((dateGroup) => (
            <section key={dateGroup.key}>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t(`Expenses.Groups.${dateGroup.key}`, dateGroup.label)}
              </h3>
              <div className="flex flex-col gap-2">
                {dateGroup.expenses.map((expense) => (
                  <ExpenseCard
                    key={expense.id}
                    expense={expense}
                    participants={group.participants || []}
                    categories={categories}
                    group={group}
                    activeUserId={activeUserId}
                    locale={i18n.resolvedLanguage || 'en-US'}
                  />
                ))}
              </div>
            </section>
          ))}
          {total > items.length ? (
            <p className="text-center text-xs text-muted-foreground">
              {t('Expenses.showingCount', 'Showing {{shown}} of {{total}} expenses.', {
                shown: items.length,
                total,
              })}
            </p>
          ) : null}
        </div>
      )}
    </section>
  )
}
