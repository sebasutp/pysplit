/** A single group row with star/archive/remove actions. */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useToast } from '../../hooks/useToast'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

/**
 * @param {{
 *   group: {id: string, name: string},
 *   detail?: any,
 *   isStarred: boolean,
 *   isArchived: boolean,
 *   onStar: (groupId: string, value: boolean) => void | Promise<void>,
 *   onArchive: (groupId: string, value: boolean) => void | Promise<void>,
 *   onRemove: (groupId: string) => void | Promise<void>
 * }} props
 */
export function RecentGroupListCard({
  group,
  detail,
  isStarred,
  isArchived,
  onStar,
  onArchive,
  onRemove,
}) {
  const { t, i18n } = useTranslation()
  const { toast } = useToast()
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const participants = detail?.participants?.length ?? detail?.participants_count ?? null
  const createdAt = detail?.created_at ? new Date(detail.created_at) : null

  return (
    <li>
      <Card className="h-fit w-full py-3">
        <div className="flex flex-col gap-1 px-3">
          <div className="flex items-start justify-between gap-2">
            <Link
              to={`/groups/${group.id}`}
              className="flex-1 overflow-hidden text-ellipsis font-medium hover:text-primary"
            >
              {group.name}
            </Link>
            <div className="flex flex-shrink-0 items-center">
              <Button
                size="icon"
                variant="ghost"
                aria-label={
                  isStarred
                    ? t('Groups.unstar', 'Unstar group')
                    : t('Groups.star', 'Star group')
                }
                aria-pressed={isStarred}
                onClick={(event) => {
                  event.stopPropagation()
                  void onStar(group.id, !isStarred)
                }}
              >
                <span className={isStarred ? 'text-amber-400' : 'text-muted-foreground'}>
                  {isStarred ? '★' : '☆'}
                </span>
              </Button>
              <div className="relative">
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label={t('Groups.moreOptions', 'More options')}
                  aria-haspopup="menu"
                  aria-expanded={menuOpen}
                  onClick={(event) => {
                    event.stopPropagation()
                    setMenuOpen((value) => !value)
                  }}
                >
                  ⋯
                </Button>
                {menuOpen ? (
                  <div
                    role="menu"
                    className="absolute right-0 top-9 z-40 w-52 rounded-md border border-border bg-popover p-1 text-sm shadow-lg"
                  >
                    <button
                      type="button"
                      role="menuitem"
                      className="block w-full rounded px-2 py-1.5 text-left hover:bg-accent"
                      onClick={() => {
                        setMenuOpen(false)
                        void onArchive(group.id, !isArchived)
                      }}
                    >
                      {isArchived
                        ? t('Groups.unarchive', 'Unarchive group')
                        : t('Groups.archive', 'Archive group')}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className="block w-full rounded px-2 py-1.5 text-left text-destructive hover:bg-accent"
                      onClick={() => {
                        setMenuOpen(false)
                        void onRemove(group.id)
                        toast({
                          title: t('Groups.RecentRemovedToast.title', 'Group has been removed'),
                          description: t(
                            'Groups.RecentRemovedToast.description',
                            'The group was removed from your recent groups list.',
                          ),
                        })
                        navigate('/groups')
                      }}
                    >
                      {t('Groups.removeRecent', 'Remove from recent groups')}
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          </div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              {participants === null ? '—' : `${participants} ${t('Groups.participants', 'participants')}`}
            </span>
            <span>
              {createdAt
                ? createdAt.toLocaleDateString(i18n.resolvedLanguage, { dateStyle: 'medium' })
                : '—'}
            </span>
          </div>
        </div>
      </Card>
    </li>
  )
}
