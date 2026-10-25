/** Application header. */

import { Link, NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { APP_NAME } from '../../services/config'
import { UserMenu } from '../auth/UserMenu'
import { LocaleSwitcher } from '../system/LocaleSwitcher'
import { ThemeToggle } from '../system/ThemeToggle'

export function Header() {
  const { t } = useTranslation()
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-5xl items-center gap-4 px-4">
        <Link to="/groups" className="text-lg font-semibold tracking-tight">
          {APP_NAME}
        </Link>
        <nav aria-label="Menu" className="flex items-center gap-1 text-sm">
          <NavLink
            to="/groups"
            className={({ isActive }) =>
              `rounded-md px-2 py-1 hover:bg-accent ${isActive ? 'text-primary' : ''}`
            }
          >
            {t('Header.groups', 'Groups')}
          </NavLink>
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <LocaleSwitcher />
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
    </header>
  )
}
