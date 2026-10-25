/** Recent, starred and archived group list. */

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useGroups } from '../../hooks/useGroups'
import { EmptyState, LoadingState } from '../common/States'
import { buttonVariants } from '../ui/Button'
import { AddGroupByUrlButton } from './AddGroupByUrlButton'
import { GlobalBalanceCard } from './GlobalBalanceCard'
import { RecentGroupListCard } from './RecentGroupListCard'

export function RecentGroupList() {
  const { t } = useTranslation()
  const state = useGroups()
  const { groups, starredGroups, archivedGroups, details } = state

  if (state.status === 'pending') {
    return (
      <>
        <GroupsHeader reload={state.reload} />
        <LoadingState label={t('Groups.loadingRecent', 'Loading recent groups…')} />
      </>
    )
  }

  if (groups.length === 0) {
    return (
      <>
        <GroupsHeader reload={state.reload} />
        <EmptyState
          title={t('Groups.NoRecent.description', 'You have not visited any group recently.')}
          description={t(
            'Groups.NoRecent.orAsk',
            'or ask a friend to send you the link to an existing one.',
          )}
          action={
            <Link to="/groups/create" className={buttonVariants({ variant: 'default' })}>
              {t('Groups.NoRecent.create', 'Create one')}
            </Link>
          }
        />
      </>
    )
  }

  const starred = []
  const regular = []
  const archived = []
  for (const group of groups) {
    if (starredGroups.includes(group.id)) starred.push(group)
    else if (archivedGroups.includes(group.id)) archived.push(group)
    else regular.push(group)
  }

  /** @param {{id: string, name: string}[]} list */
  const renderList = (list) => (
    <ul className="grid gap-2 sm:grid-cols-2">
      {list.map((group) => (
        <RecentGroupListCard
          key={group.id}
          group={group}
          detail={details.find((item) => item.id === group.id)}
          isStarred={starredGroups.includes(group.id)}
          isArchived={archivedGroups.includes(group.id)}
          onStar={state.setStarred}
          onArchive={state.setArchived}
          onRemove={state.remove}
        />
      ))}
    </ul>
  )

  return (
    <>
      <GroupsHeader reload={state.reload} />
      <GlobalBalanceCard groups={groups} />
      {starred.length ? (
        <section>
          <h2 className="mb-2 font-semibold">{t('Groups.starred', 'Starred groups')}</h2>
          {renderList(starred)}
        </section>
      ) : null}
      {regular.length ? (
        <section className={starred.length ? 'mt-6' : ''}>
          <h2 className="mb-2 font-semibold">{t('Groups.recent', 'Recent groups')}</h2>
          {renderList(regular)}
        </section>
      ) : null}
      {archived.length ? (
        <section className="mt-6">
          <h2 className="mb-2 font-semibold opacity-50">
            {t('Groups.archived', 'Archived groups')}
          </h2>
          <div className="opacity-50">{renderList(archived)}</div>
        </section>
      ) : null}
    </>
  )
}

/** @param {{reload: () => void | Promise<void>}} props */
function GroupsHeader({ reload }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
      <h1 className="flex-1 text-2xl font-bold">
        <Link to="/groups">{t('Groups.myGroups', 'My groups')}</Link>
      </h1>
      <div className="flex gap-2">
        <AddGroupByUrlButton reload={reload} />
        <Link to="/groups/create" className={buttonVariants({ variant: 'default' })}>
          {t('Groups.create', 'Create')}
        </Link>
      </div>
    </div>
  )
}
