/** Server-enforced runtime feature flags. */

import { useEffect, useState } from 'react'

import { repository } from '../services/repository'

const DISABLED = {
  receipt_extract: false,
  receipt_items: false,
  category_extract: false,
  expense_documents: false,
}

/** @type {Promise<any>|null} */
let featuresRequest = null

/** Load the flags once per process and share the in-flight promise. */
function loadFeatures() {
  if (!featuresRequest) {
    featuresRequest = repository.features.get().catch((error) => {
      // Allow a later mount to retry after a transient failure.
      featuresRequest = null
      throw error
    })
  }
  return featuresRequest
}

/** Drop the cached flags (used after a reload and by tests). */
export function clearFeaturesCache() {
  featuresRequest = null
}

/** @returns {{features: typeof DISABLED, loading: boolean}} */
export function useFeatures() {
  const [features, setFeatures] = useState(/** @type {typeof DISABLED} */ (DISABLED))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    loadFeatures()
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
