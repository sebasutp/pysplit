import { afterEach, describe, expect, it, vi } from 'vitest'

import { compressImage } from '../utils/compress-image'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('compressImage', () => {
  it('compresses large images', async () => {
    const original = new Blob([new Uint8Array(2_000_000)], { type: 'image/jpeg' })
    const compressed = new Blob(['small'], { type: 'image/jpeg' })
    vi.stubGlobal(
      'createImageBitmap',
      vi.fn(async () => ({ width: 4000, height: 3000, close: vi.fn() })),
    )
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      /** @type {any} */ ({ drawImage: vi.fn() }),
    )
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((callback) => {
      callback(compressed)
    })

    const result = await compressImage(original, { maxDimension: 800 })
    expect(result).toBe(compressed)
    expect(result.size).toBeLessThan(original.size)
  })
})
