import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { LoadingState } from './components/common/States'

/**
 * Turn a named page export into a lazily loaded route component, so every page
 * lives in its own chunk instead of the entry bundle.
 *
 * @param {() => Promise<Record<string, any>>} loader
 * @param {string} name
 * @returns {React.LazyExoticComponent<React.ComponentType<any>>}
 */
function lazyPage(loader, name) {
  return lazy(async () => {
    const page = await loader()
    return { default: page[name] }
  })
}

const PlaceholderPage = lazyPage(() => import('./pages/PlaceholderPage'), 'PlaceholderPage')
const CreateGroupPage = lazyPage(() => import('./pages/CreateGroupPage'), 'CreateGroupPage')
const GroupsPage = lazyPage(() => import('./pages/GroupsPage'), 'GroupsPage')
const AdminPage = lazyPage(() => import('./pages/AdminPage'), 'AdminPage')
const GroupLayout = lazyPage(() => import('./components/groups/GroupLayout'), 'GroupLayout')
const ActivityPage = lazyPage(() => import('./pages/group/ActivityPage'), 'ActivityPage')
const BalancesPage = lazyPage(() => import('./pages/group/BalancesPage'), 'BalancesPage')
const ExpenseCreatePage = lazyPage(
  () => import('./pages/group/ExpenseCreatePage'),
  'ExpenseCreatePage',
)
const ExpenseEditPage = lazyPage(() => import('./pages/group/ExpenseEditPage'), 'ExpenseEditPage')
const ExpensesPage = lazyPage(() => import('./pages/group/ExpensesPage'), 'ExpensesPage')
const GroupSettingsPage = lazyPage(
  () => import('./pages/group/GroupSettingsPage'),
  'GroupSettingsPage',
)
const InformationPage = lazyPage(() => import('./pages/group/InformationPage'), 'InformationPage')
const ReceiptItemsPage = lazyPage(() => import('./pages/group/ReceiptItemsPage'), 'ReceiptItemsPage')
const StatsPage = lazyPage(() => import('./pages/group/StatsPage'), 'StatsPage')

/**
 * A route element with its own Suspense boundary. Keeping the boundary on the
 * element (rather than once around <Routes>) means a nested page chunk resolves
 * inside the group layout's <Outlet>, so the layout and its data stay mounted.
 *
 * @param {{component: React.LazyExoticComponent<React.ComponentType<any>>}} props
 */
function LazyRoute({ component: Component }) {
  return (
    <Suspense fallback={<LoadingState />}>
      <Component />
    </Suspense>
  )
}

/**
 * Route table. Paths preserve the reference URL scheme so existing shared
 * links keep working.
 */
export function AppRoutes() {
  const { t } = useTranslation()
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/groups" replace />} />
      <Route path="/groups" element={<LazyRoute component={GroupsPage} />} />
      <Route path="/groups/create" element={<LazyRoute component={CreateGroupPage} />} />
      <Route path="/groups/:groupId" element={<LazyRoute component={GroupLayout} />}>
        <Route index element={<GroupRedirect />} />
        <Route path="expenses" element={<LazyRoute component={ExpensesPage} />} />
        <Route
          path="expenses/create"
          element={<LazyRoute component={ExpenseCreatePage} />}
        />
        <Route
          path="expenses/:expenseId/edit"
          element={<LazyRoute component={ExpenseEditPage} />}
        />
        <Route
          path="expenses/:expenseId/items"
          element={<LazyRoute component={ReceiptItemsPage} />}
        />
        <Route path="balances" element={<LazyRoute component={BalancesPage} />} />
        <Route path="stats" element={<LazyRoute component={StatsPage} />} />
        <Route path="activity" element={<LazyRoute component={ActivityPage} />} />
        <Route path="information" element={<LazyRoute component={InformationPage} />} />
        <Route path="edit" element={<LazyRoute component={GroupSettingsPage} />} />
      </Route>
      <Route path="/admin" element={<LazyRoute component={AdminPage} />} />
      <Route
        path="*"
        element={
          <Suspense fallback={<LoadingState />}>
            <PlaceholderPage
              title={t('NotFound.title', 'Page not found')}
              description={t('NotFound.description', 'Check the URL and try again.')}
            />
          </Suspense>
        }
      />
    </Routes>
  )
}

function GroupRedirect() {
  const { groupId } = useParams()
  return <Navigate to={`/groups/${groupId}/expenses`} replace />
}
