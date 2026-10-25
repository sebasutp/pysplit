/** /groups/:groupId/expenses/:expenseId/edit */

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { useGroupContext } from '../../components/groups/GroupLayout'
import { ExpenseForm } from '../../components/expenses/ExpenseForm'
import { ErrorState, LoadingState } from '../../components/common/States'
import { useActiveUser } from '../../hooks/useActiveUser'
import { useCategories } from '../../hooks/useCategories'
import { useFeatures } from '../../hooks/useFeatures'
import { repository } from '../../services/repository'

export function ExpenseEditPage() {
  const { group } = useGroupContext()
  const { activeUserId } = useActiveUser(group.id)
  const { expenseId } = useParams()
  const { categories, loading: categoriesLoading } = useCategories()
  const { features } = useFeatures()
  const [expense, setExpense] = useState(/** @type {any|null} */ (null))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(/** @type {any} */ (null))

  useEffect(() => {
    // Clear the previous expense before loading a different one so the form
    // can never render or PATCH the wrong record.
    setExpense(null)
    setLoading(true)
    setError(null)
    if (!expenseId) {
      setLoading(false)
      return undefined
    }
    const controller = new AbortController()
    repository.expenses
      .get(group.id, expenseId, { signal: controller.signal })
      .then((payload) => {
        if (controller.signal.aborted) return
        setExpense(payload)
        setLoading(false)
      })
      .catch((caught) => {
        if (caught && typeof caught === 'object' && caught.code === 'aborted') return
        if (controller.signal.aborted) return
        setError(caught)
        setLoading(false)
      })
    return () => controller.abort()
  }, [group.id, expenseId])

  if (loading || categoriesLoading) return <LoadingState />
  if (error) return <ErrorState detail={error.detail || error.message} />
  if (!expense) return <ErrorState title="Expense not found" />

  return (
    <ExpenseForm
      key={expense.id}
      group={group}
      categories={categories}
      expense={expense}
      activeUserId={activeUserId}
      features={features}
    />
  )
}
