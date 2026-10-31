import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { clearCategoriesCache, useCategories } from './useCategories'
import { clearFeaturesCache, useFeatures } from './useFeatures'

const { featuresGet, categoriesList } = vi.hoisted(() => ({
  featuresGet: vi.fn(),
  categoriesList: vi.fn(),
}))

vi.mock('../services/repository', () => ({
  repository: {
    features: { get: featuresGet },
    categories: { list: categoriesList },
  },
}))

beforeEach(() => {
  clearFeaturesCache()
  clearCategoriesCache()
  featuresGet.mockReset()
  categoriesList.mockReset()
})

describe('feature and category caches', () => {
  it('shares one feature request between mounts until cleared', async () => {
    featuresGet.mockResolvedValue({ receipt_ai: true })

    const first = renderHook(() => useFeatures())
    await waitFor(() => expect(first.result.current.loading).toBe(false))
    expect(first.result.current.features.receipt_ai).toBe(true)

    const second = renderHook(() => useFeatures())
    await waitFor(() => expect(second.result.current.loading).toBe(false))
    expect(featuresGet).toHaveBeenCalledTimes(1)

    clearFeaturesCache()
    const third = renderHook(() => useFeatures())
    await waitFor(() => expect(third.result.current.loading).toBe(false))
    expect(featuresGet).toHaveBeenCalledTimes(2)
  })

  it('shares one category request between mounts until cleared', async () => {
    categoriesList.mockResolvedValue({ items: [{ id: 1, name: 'Food' }] })

    const first = renderHook(() => useCategories())
    await waitFor(() => expect(first.result.current.loading).toBe(false))
    expect(first.result.current.categories).toEqual([{ id: 1, name: 'Food' }])

    const second = renderHook(() => useCategories())
    await waitFor(() => expect(second.result.current.loading).toBe(false))
    expect(categoriesList).toHaveBeenCalledTimes(1)

    clearCategoriesCache()
    const third = renderHook(() => useCategories())
    await waitFor(() => expect(third.result.current.loading).toBe(false))
    expect(categoriesList).toHaveBeenCalledTimes(2)
  })
})
