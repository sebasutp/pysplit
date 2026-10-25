/**
 * Downscale an image in the browser before upload.
 *
 * The reference uses canvas compression for receipt and document photos. The
 * helper is intentionally dependency-free and resolves to the original file
 * whenever the environment cannot decode or encode images (SSR, tests).
 */

export const DEFAULT_MAX_DIMENSION = 1600
export const DEFAULT_QUALITY = 0.82

/**
 * @param {Blob} file
 * @param {{maxDimension?: number, quality?: number, mimeType?: string}} [options]
 * @returns {Promise<Blob>}
 */
export async function compressImage(file, options = {}) {
  const maxDimension = options.maxDimension ?? DEFAULT_MAX_DIMENSION
  const quality = options.quality ?? DEFAULT_QUALITY
  const mimeType = options.mimeType || 'image/jpeg'

  if (typeof document === 'undefined' || typeof createImageBitmap !== 'function') return file

  let bitmap
  try {
    bitmap = await createImageBitmap(file)
  } catch {
    return file
  }

  const scale = Math.min(1, maxDimension / Math.max(bitmap.width, bitmap.height))
  const width = Math.max(1, Math.round(bitmap.width * scale))
  const height = Math.max(1, Math.round(bitmap.height * scale))
  if (scale === 1 && file.size < 512 * 1024) {
    bitmap.close?.()
    return file
  }

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) {
    bitmap.close?.()
    return file
  }
  context.drawImage(bitmap, 0, 0, width, height)
  bitmap.close?.()

  const blob = await new Promise((resolve) => {
    canvas.toBlob((result) => resolve(result), mimeType, quality)
  })
  if (!blob) return file
  return blob
}

/**
 * @param {Blob|File} file
 * @returns {Promise<{width: number, height: number}>}
 */
export async function imageDimensions(file) {
  if (typeof createImageBitmap !== 'function') return { width: 1, height: 1 }
  try {
    const bitmap = await createImageBitmap(file)
    const result = { width: bitmap.width, height: bitmap.height }
    bitmap.close?.()
    return result
  } catch {
    return { width: 1, height: 1 }
  }
}
