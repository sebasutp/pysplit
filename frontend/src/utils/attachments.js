/** Prepare an image or PDF for upload. */

import { IMAGE_MAX_DIMENSION, IMAGE_QUALITY } from '../services/config'
import { compressImage, imageDimensions } from './compress-image'

export const PDF_CONTENT_TYPE = 'application/pdf'

/**
 * Compress images in the browser and leave PDFs untouched.
 *
 * @param {File} file
 * @returns {Promise<{file: File|Blob, width: number, height: number, contentType: string}>}
 */
export async function prepareUpload(file) {
  const type = String(file.type || '').toLowerCase()
  if (type === PDF_CONTENT_TYPE) {
    return { file, width: 1, height: 1, contentType: PDF_CONTENT_TYPE }
  }
  if (!type.startsWith('image/')) {
    throw new Error('Only images and PDF files are supported.')
  }

  const compressed = await compressImage(file, {
    maxDimension: IMAGE_MAX_DIMENSION,
    quality: IMAGE_QUALITY,
  })
  const dimensions = await imageDimensions(compressed)
  const prepared =
    typeof File !== 'undefined' && compressed instanceof File
      ? compressed
      : new File([compressed], file.name || 'image.jpg', {
          type: compressed.type || type || 'image/jpeg',
        })
  return {
    file: prepared,
    width: dimensions.width,
    height: dimensions.height,
    contentType: prepared.type || type || 'image/jpeg',
  }
}

/** @param {any} attachment */
export function isPdf(attachment) {
  return attachment?.content_type === PDF_CONTENT_TYPE
}

/** @param {any} attachment */
export function attachmentLabel(attachment) {
  return attachment?.filename || attachment?.id || 'Attachment'
}

/** @param {number} size */
export function formatBytes(size) {
  const value = Number(size || 0)
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}
