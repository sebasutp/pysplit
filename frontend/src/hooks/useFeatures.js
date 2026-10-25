/** Server-enforced runtime feature flags. */

import { useEffect, useState } from 'react'

import { repository } from '../services/repository'

const DISABLED = {
  receipt_extract: false,
  receipt_items: false,
  category_extract: false,
  expense_documents: false,
}

/** @returns {{features: typeof DISABLED, loading: boolean}} */
export function useFeatures() {
  const [features, setFeatures] = useState(/** @type {typeof DISABLED} */ (DISABLED))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    repository.features
      .get()
      .then((payload) => {
        if (active) setFeatures({ ...DISABLED, ...payload })
      })
      .catch(() => {
        // Disabled is the safe default when the API is unreachable.
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  return { features, loading }
}
