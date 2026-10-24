import { Link, NavLink } from 'react-router-dom'

import { HealthIndicator } from './components/system/HealthIndicator'
import { AppRoutes } from './router'
import { APP_NAME } from './services/config'

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 px-4 py-3">
          <Link to="/groups" className="text-lg font-semibold tracking-tight">
            {APP_NAME}
          </Link>
          <nav aria-label="Main" className="flex items-center gap-3 text-sm">
            <NavLink className="hover:text-primary" to="/groups">
              Groups
            </NavLink>
            <NavLink className="hover:text-primary" to="/admin">
              Admin
            </NavLink>
          </nav>
          <div className="ml-auto">
            <HealthIndicator />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">
        <AppRoutes />
      </main>
    </div>
  )
}
