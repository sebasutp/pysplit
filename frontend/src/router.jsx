import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { PlaceholderPage } from './pages/PlaceholderPage'
import { CreateGroupPage } from './pages/CreateGroupPage'
import { GroupsPage } from './pages/GroupsPage'
import { AdminPage } from './pages/AdminPage'
import { GroupLayout } from './components/groups/GroupLayout'
import { ActivityPage } from './pages/group/ActivityPage'
import { BalancesPage } from './pages/group/BalancesPage'
import { ExpenseCreatePage } from './pages/group/ExpenseCreatePage'
import { ExpenseEditPage } from './pages/group/ExpenseEditPage'
import { ExpensesPage } from './pages/group/ExpensesPage'
import { GroupSettingsPage } from './pages/group/GroupSettingsPage'
import { InformationPage } from './pages/group/InformationPage'
import { ReceiptItemsPage } from './pages/group/ReceiptItemsPage'
import { StatsPage } from './pages/group/StatsPage'

/**
 * Route table. Paths preserve the reference URL scheme so existing shared
 * links keep working.
 */
export function AppRoutes() {
  const { t } = useTranslation()
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/groups" replace />} />
      <Route path="/groups" element={<GroupsPage />} />
      <Route path="/groups/create" element={<CreateGroupPage />} />
      <Route path="/groups/:groupId" element={<GroupLayout />}>
        <Route index element={<GroupRedirect />} />
        <Route path="expenses" element={<ExpensesPage />} />
        <Route path="expenses/create" element={<ExpenseCreatePage />} />
        <Route path="expenses/:expenseId/edit" element={<ExpenseEditPage />} />
        <Route path="expenses/:expenseId/items" element={<ReceiptItemsPage />} />
        <Route path="balances" element={<BalancesPage />} />
        <Route path="stats" element={<StatsPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="information" element={<InformationPage />} />
        <Route path="edit" element={<GroupSettingsPage />} />
      </Route>
      <Route path="/admin" element={<AdminPage />} />
      <Route
        path="*"
        element={
          <PlaceholderPage
            title={t('NotFound.title', 'Page not found')}
            description={t('NotFound.description', 'Check the URL and try again.')}
          />
        }
      />
    </Routes>
  )
}

function GroupRedirect() {
  const { groupId } = useParams()
  return <Navigate to={`/groups/${groupId}/expenses`} replace />
}
