/** Seeded expense categories, fetched once per page mount. */

import { useEffect, useState } from 'react'

import { repository } from '../services/repository'

/** @returns {{categories: any[], loading: boolean, error: any}} */
export function useCategories() {
  const [categories, setCategories] = useState(/** @type {any[]} */ ([]))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(/** @type {any} */ (null))

  useEffect(() => {
    const controller = new AbortController()
    repository.categories
      .list({ signal: controller.signal })
      .then((payload) => setCategories(payload?.items || payload || []))
      .catch((caught) => {
        if (caught && typeof caught === 'object' && caught.code === 'aborted') return
        setError(caught)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [])

  return { categories, loading, error }
}

/** @param {any[]} categories @param {number|null|undefined} categoryId */
export function categoryName(categories, categoryId) {
  return categories.find((category) => category.id === categoryId)?.name || 'General'
}

/** @param {any[]} categories */
export function categoryOptions(categories) {
  return categories.map((category) => ({
    value: category.id,
    label: category.name,
  }))
}
