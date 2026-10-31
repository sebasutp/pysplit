/** Group title, share action and tab navigation. */

import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { Button } from '../ui/Button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/Dialog'
import { Input } from '../ui/Input'

/** @type {{key: string, path: string}[]} */
const TABS = [
  { key: 'Expenses', path: 'expenses' },
  { key: 'Balances', path: 'balances' },
  { key: 'Information', path: 'information' },
  { key: 'Stats', path: 'stats' },
  { key: 'Activity', path: 'activity' },
  { key: 'Settings', path: 'edit' },
]

/** @param {any} group */
function visibleTabs(group) {
  const hasInformation =
    typeof group?.information === 'string' && group.information.trim().length > 0
  return TABS.filter((tab) => tab.key !== 'Information' || hasInformation)
}

/**
 * @param {{group: any}} props
 */
export function GroupHeader({ group }) {
  const { t } = useTranslation()
  const [shareOpen, setShareOpen] = useState(false)
  const url = typeof window === 'undefined' ? '' : `${window.location.origin}/groups/${group.id}`
  const tabs = visibleTabs(group)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold tracking-tight">{group.name}</h1>
        <Button variant="outline" size="sm" onClick={() => setShareOpen(true)}>
          {t('Share.button', 'Share')}
        </Button>
      </div>

      <nav
        role="tablist"
        aria-label={t('GroupTabs.label', 'Group sections')}
        className="flex flex-wrap gap-1 border-b border-border pb-1"
      >
        {tabs.map((tab) => (
          <NavLink
            key={tab.key}
            role="tab"
            to={`/groups/${group.id}/${tab.path}`}
            className={({ isActive }) =>
              `rounded-t-md px-3 py-1.5 text-sm ${
                isActive
                  ? 'border-b-2 border-primary font-medium text-primary'
                  : 'text-muted-foreground hover:text-foreground'
              }`
            }
          >
            {t(`GroupTabs.${tab.key}`, tab.key)}
          </NavLink>
        ))}
      </nav>

      <Dialog open={shareOpen} onOpenChange={setShareOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('Share.title', 'Share this group')}</DialogTitle>
            <DialogDescription>
              {t(
                'Share.description',
                'Anyone with this link can view and edit the group. The link is the only access control.',
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4 flex gap-2">
            <Input readOnly value={url} aria-label={t('Share.url', 'Group link')} />
            <Button
              type="button"
              onClick={() => {
                void navigator.clipboard?.writeText(url)
                setShareOpen(false)
              }}
            >
              {t('Share.copy', 'Copy link')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
