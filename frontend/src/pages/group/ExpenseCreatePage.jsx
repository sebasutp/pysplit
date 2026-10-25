/** /groups/:groupId/expenses/create */

import { useGroupContext } from '../../components/groups/GroupLayout'
import { ExpenseForm } from '../../components/expenses/ExpenseForm'
import { LoadingState } from '../../components/common/States'
import { useActiveUser } from '../../hooks/useActiveUser'
import { useCategories } from '../../hooks/useCategories'
import { useFeatures } from '../../hooks/useFeatures'

export function ExpenseCreatePage() {
  const { group } = useGroupContext()
  const { activeUserId } = useActiveUser(group.id)
  const { categories, loading } = useCategories()
  const { features } = useFeatures()
  if (loading && !categories.length) return <LoadingState />
  return (
    <ExpenseForm
      group={group}
      categories={categories}
      activeUserId={activeUserId}
      features={features}
    />
  )
}
