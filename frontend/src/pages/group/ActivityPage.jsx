/** /groups/:groupId/activity */

import { useTranslation } from 'react-i18next'

import { useGroupContext } from '../../components/groups/GroupLayout'
import { ErrorState, LoadingState } from '../../components/common/States'
import { useActivities } from '../../hooks/useActivities'
import { Button } from '../../components/ui/Button'

/**
 * @param {any} activity
 * @param {string} participantName
 * @returns {string}
 */
function activityText(activity, participantName) {
  const title = activity.expense?.title || activity.data || ''
  switch (activity.activity_type) {
    case 'CREATE_EXPENSE':
      return `Expense “${title}” created by ${participantName}.`
    case 'UPDATE_EXPENSE':
      return `Expense “${title}” updated by ${participantName}.`
    case 'DELETE_EXPENSE':
      return `Expense “${title}” deleted by ${participantName}.`
    case 'UPDATE_GROUP':
      return `Group settings were modified by ${participantName}.`
    default:
      return title || activity.activity_type
  }
}

export function ActivityPage() {
  const { group } = useGroupContext()
  const { t, i18n } = useTranslation()
  const { items, loading, error, hasMore, loadMore } = useActivities(group.id)
  const participants = group.participants || []

  if (loading) return <LoadingState label={t('Activity.loading', 'Loading activity…')} />
  if (error) return <ErrorState detail={error.detail || error.message} />

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h2 className="text-xl font-semibold">{t('Activity.title', 'Activity')}</h2>
        <p className="text-sm text-muted-foreground">
          {t('Activity.description', 'Overview of all activity in this group.')}
        </p>
      </div>
      {items.length ? (
        <>
          <ul className="flex flex-col divide-y divide-border rounded-lg border border-border bg-card">
            {items.map((activity) => {
              const actor =
                participants.find(
                  (/** @type {any} */ participant) =>
                    participant.id === activity.participant_id,
                )?.name || t('Activity.someone', 'Someone')
              const time = new Date(activity.time)
              return (
                <li key={activity.id} className="flex flex-col gap-1 p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
                  <span>{activityText(activity, actor)}</span>
                  <span className="text-xs text-muted-foreground">
                    {Number.isNaN(time.getTime())
                      ? ''
                      : time.toLocaleString(i18n.resolvedLanguage, { dateStyle: 'medium', timeStyle: 'short' })}
                  </span>
                </li>
              )
            })}
          </ul>
          {hasMore ? (
            <Button variant="outline" onClick={() => void loadMore()}>
              {t('Activity.loadMore', 'Load more')}
            </Button>
          ) : null}
        </>
      ) : (
        <p className="text-sm text-muted-foreground">
          {t('Activity.noActivity', 'There is not yet any activity in your group.')}
        </p>
      )}
    </section>
  )
}
