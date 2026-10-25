import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { PlaceholderPage } from './pages/PlaceholderPage'
import { CreateGroupPage } from './pages/CreateGroupPage'
import { GroupsPage } from './pages/GroupsPage'

/**
 * Route table. Paths preserve the reference URL scheme so existing shared
 * links keep working. Later stages replace the placeholder content while the
 * paths stay frozen.
 */
export function AppRoutes() {
  const { t } = useTranslation()
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/groups" replace />} />
      <Route path="/groups" element={<GroupsPage />} />
      <Route path="/groups/create" element={<CreateGroupPage />} />
      <Route path="/groups/:groupId" element={<GroupRedirect />} />
      <Route
        path="/groups/:groupId/expenses"
        element={
          <PlaceholderPage
            title={t('GroupTabs.Expenses', 'Expenses')}
            description={t(
              'Stage.eightBexpenses',
              'The expense list is implemented in Stage 8B.',
            )}
          />
        }
      />
      <Route
        path="/groups/:groupId/expenses/create"
        element={
          <PlaceholderPage
            title={t('Expenses.create', 'Create expense')}
            description={t('Stage.eightBform', 'The expense form is implemented in Stage 8B.')}
          />
        }
      />
      <Route
        path="/groups/:groupId/expenses/:expenseId/edit"
        element={
          <PlaceholderPage
            title={t('Expenses.edit', 'Edit expense')}
            description={t('Stage.eightBform', 'The expense form is implemented in Stage 8B.')}
          />
        }
      />
      <Route
        path="/groups/:groupId/expenses/:expenseId/items"
        element={
          <PlaceholderPage
            title={t('ReceiptItems.title', 'Receipt items')}
            description={t('Stage.eightD', 'Smart split is implemented in Stage 8D.')}
          />
        }
      />
      <Route
        path="/groups/:groupId/balances"
        element={
          <PlaceholderPage
            title={t('Balances.title', 'Balances')}
            description={t('Stage.eightC', 'Balances are implemented in Stage 8C.')}
          />
        }
      />
      <Route
        path="/groups/:groupId/stats"
        element={
          <PlaceholderPage
            title={t('Stats.title', 'Statistics')}
            description={t('Stage.eightCstats', 'Statistics are implemented in Stage 8C.')}
          />
        }
      />
      <Route
        path="/groups/:groupId/activity"
        element={
          <PlaceholderPage
            title={t('Activity.title', 'Activity')}
            description={t('Stage.eightB', 'The activity log is implemented in Stage 8B.')}
          />
        }
      />
      <Route
        path="/groups/:groupId/information"
        element={
          <PlaceholderPage
            title={t('Information.title', 'Group information')}
            description={t('Stage.eightBinfo', 'Group details are implemented in Stage 8B.')}
          />
        }
      />
      <Route
        path="/groups/:groupId/edit"
        element={
          <PlaceholderPage
            title={t('Settings.title', 'Settings')}
            description={t('Stage.eightBedit', 'Group editing is implemented in Stage 8B.')}
          />
        }
      />
      <Route
        path="/admin"
        element={
          <PlaceholderPage
            title={t('Admin.title', 'Admin')}
            description={t('Stage.eightDadmin', 'Administration is implemented in Stage 8D.')}
          />
        }
      />
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
