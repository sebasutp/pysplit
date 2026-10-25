/** Debounce a rapidly changing value (search boxes, filters). */

import { useEffect, useState } from 'react'

/**
 * @template T
 * @param {T} value
 * @param {number} [delay] milliseconds
 * @returns {T}
 */
export function useDebouncedValue(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}
