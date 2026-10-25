/**
 * Account menu in the application header.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useAuth } from '../../hooks/useAuth'
import { Button } from '../ui/Button'
import { Badge, Skeleton } from '../ui/Feedback'
import { LoginDialog } from './LoginDialog'

const TIER_LABELS = /** @type {Record<string, string>} */ ({
  admin: 'Admin',
  group_creators: 'Creator',
  sync_users: 'Sync',
})

export function UserMenu() {
  const { t } = useTranslation()
  const { user, loading, isAdmin, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const container = useRef(/** @type {HTMLDivElement | null} */ (null))
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) return undefined
    /** @param {MouseEvent} event */
    const onClick = (event) => {
      if (container.current && event.target instanceof Node && !container.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const handleLogout = useCallback(async () => {
    setOpen(false)
    await logout()
    navigate('/groups')
  }, [logout, navigate])

  if (loading) return <Skeleton className="h-8 w-8 rounded-full" />

  if (!user) {
    return (
      <LoginDialog
        trigger={
          <Button variant="outline" size="sm">
            {t('Header.signIn', 'Sign in')}
          </Button>
        }
      />
    )
  }

  const initial = (user.name || 'U').charAt(0).toUpperCase()

  return (
    <div ref={container} className="relative">
      <button
        type="button"
        aria-label={t('Header.userMenu', 'User menu')}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full border border-border bg-primary/10 text-xs font-semibold text-primary"
        onClick={() => setOpen((value) => !value)}
      >
        {user.image ? (
          <img src={user.image} alt={user.name || 'User'} className="h-8 w-8 object-cover" />
        ) : (
          initial
        )}
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-10 z-40 w-56 rounded-md border border-border bg-popover p-2 text-popover-foreground shadow-lg"
        >
          <div className="flex items-start justify-between gap-2 px-2 py-1.5">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{user.name || 'User'}</p>
              {user.email ? (
                <p className="truncate text-xs text-muted-foreground">{user.email}</p>
              ) : null}
            </div>
            <Badge
              variant={
                user.tier === 'admin'
                  ? 'destructive'
                  : user.tier === 'group_creators'
                    ? 'default'
                    : 'secondary'
              }
            >
              {TIER_LABELS[user.tier] || user.tier}
            </Badge>
          </div>
          {isAdmin ? (
            <Link
              role="menuitem"
              to="/admin"
              className="block rounded px-2 py-1.5 text-sm text-primary hover:bg-accent"
              onClick={() => setOpen(false)}
            >
              {t('Header.adminDashboard', 'Admin dashboard')}
            </Link>
          ) : null}
          <button
            type="button"
            role="menuitem"
            className="block w-full rounded px-2 py-1.5 text-left text-sm text-destructive hover:bg-accent"
            onClick={handleLogout}
          >
            {t('Header.signOut', 'Sign out')}
          </button>
        </div>
      ) : null}
    </div>
  )
}
