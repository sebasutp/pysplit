/**
 * Theme selection, compatible with the reference `theme` localStorage key.
 */

import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'theme'

/** @returns {'light'|'dark'|'system'} */
function readTheme() {
  try {
    const value = localStorage.getItem(STORAGE_KEY)
    return value === 'light' || value === 'dark' ? value : 'system'
  } catch {
    return 'system'
  }
}

/** @param {'light'|'dark'|'system'} value */
function applyTheme(value) {
  if (typeof document === 'undefined') return
  const prefersDark =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  const dark = value === 'dark' || (value === 'system' && prefersDark)
  document.documentElement.classList.toggle('dark', dark)
}

export function useTheme() {
  const [theme, setThemeState] = useState(readTheme)

  useEffect(() => {
    applyTheme(theme)
    if (theme !== 'system' || typeof window === 'undefined') return undefined
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => applyTheme('system')
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [theme])

  const setTheme = useCallback(
    /** @param {'light'|'dark'|'system'} value */
    (value) => {
    setThemeState(value)
    try {
      localStorage.setItem(STORAGE_KEY, value)
    } catch {
      // ignored
    }
    applyTheme(value)
    },
    [],
  )

  return { theme, setTheme }
}
