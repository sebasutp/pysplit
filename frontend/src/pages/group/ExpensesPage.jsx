/** /groups/:groupId/expenses */

import { useGroupContext } from '../../components/groups/GroupLayout'
import { ExpenseList } from '../../components/expenses/ExpenseList'
import { useActiveUser } from '../../hooks/useActiveUser'

export function ExpensesPage() {
  const { group } = useGroupContext()
  const { activeUserId } = useActiveUser(group.id)
  return <ExpenseList group={group} activeUserId={activeUserId} />
}
