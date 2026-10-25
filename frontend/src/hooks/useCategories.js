/** Seeded expense categories, fetched once per process. */

import { useEffect, useState } from 'react'

import { repository } from '../services/repository'

/** @type {Promise<any[]>|null} */
let categoriesRequest = null

/** Load the categories once per process and share the in-flight promise. */
function loadCategories() {
  if (!categoriesRequest) {
    categoriesRequest = repository.categories
      .list()
      .then((payload) => payload?.items || payload || [])
      .catch((error) => {
        // Allow a later mount to retry after a transient failure.
        categoriesRequest = null
        throw error
      })
  }
  return categoriesRequest
}

/** Drop the cached categories (used after a reload and by tests). */
export function clearCategoriesCache() {
  categoriesRequest = null
}

/** @returns {{categories: any[], loading: boolean, error: any}} */
export function useCategories() {
  const [categories, setCategories] = useState(/** @type {any[]} */ ([]))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(/** @type {any} */ (null))

  useEffect(() => {
    let active = true
    loadCategories()
      .then((items) => {
        if (!active) return
        setCategories(items)
        setError(null)
      })
      .catch((caught) => {
        if (!active) return
        setError(caught)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  return { categories, loading, error }
}
