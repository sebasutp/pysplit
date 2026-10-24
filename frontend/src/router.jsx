import { Navigate, Route, Routes } from 'react-router-dom'

import { PagePlaceholder } from './components/common/PagePlaceholder'

/**
 * Route table. Paths preserve the reference URL scheme so existing shared
 * links keep working. Feature stages replace the placeholders; the paths
 * themselves are frozen from Stage 8A onward.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/groups" replace />} />
      <Route
        path="/groups"
        element={<PagePlaceholder title="Groups" description="Recent, starred and archived groups." />}
      />
      <Route
        path="/groups/create"
        element={<PagePlaceholder title="Create group" description="Group creation is added in Stage 8A." />}
      />
      <Route
        path="/groups/:groupId"
        element={<PagePlaceholder title="Group" description="The group overview redirects to expenses in Stage 8A." />}
      />
      <Route
        path="/groups/:groupId/expenses"
        element={<PagePlaceholder title="Expenses" description="Expense list is added in Stage 8B." />}
      />
      <Route
        path="/groups/:groupId/expenses/create"
        element={<PagePlaceholder title="New expense" description="Expense form is added in Stage 8B." />}
      />
      <Route
        path="/groups/:groupId/expenses/:expenseId/edit"
        element={<PagePlaceholder title="Edit expense" description="Expense form is added in Stage 8B." />}
      />
      <Route
        path="/groups/:groupId/expenses/:expenseId/items"
        element={<PagePlaceholder title="Receipt items" description="Smart split is added in Stage 8D." />}
      />
      <Route
        path="/groups/:groupId/balances"
        element={<PagePlaceholder title="Balances" description="Balances are added in Stage 8C." />}
      />
      <Route
        path="/groups/:groupId/stats"
        element={<PagePlaceholder title="Statistics" description="Statistics are added in Stage 8C." />}
      />
      <Route
        path="/groups/:groupId/activity"
        element={<PagePlaceholder title="Activity" description="The activity log is added in Stage 8B." />}
      />
      <Route
        path="/groups/:groupId/information"
        element={<PagePlaceholder title="Group information" description="Group details are added in Stage 8B." />}
      />
      <Route
        path="/groups/:groupId/edit"
        element={<PagePlaceholder title="Edit group" description="Group editing is added in Stage 8B." />}
      />
      <Route
        path="/admin"
        element={<PagePlaceholder title="Admin" description="Administration is added in Stage 8D." />}
      />
      <Route path="*" element={<PagePlaceholder title="Page not found" description="Check the URL and try again." />} />
    </Routes>
  )
}
