/** Light / dark / system theme selector. */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useTheme } from '../../hooks/useTheme'

const OPTIONS = [
  ['light', 'Light'],
  ['dark', 'Dark'],
  ['system', 'System'],
]

export function ThemeToggle() {
  const { t } = useTranslation()
  const { theme, setTheme } = useTheme()
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <button
        type="button"
        className="inline-flex h-8 items-center rounded-md px-2 text-sm hover:bg-accent"
        aria-label={t('Theme.toggle', 'Toggle theme')}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {theme === 'dark' ? '☾' : '☀'}
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-9 z-40 w-32 rounded-md border border-border bg-popover p-1 text-sm shadow-lg"
        >
          {OPTIONS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="menuitem"
              className="block w-full rounded px-2 py-1.5 text-left hover:bg-accent"
              onClick={() => {
                setTheme(/** @type {'light'|'dark'|'system'} */ (value))
                setOpen(false)
              }}
            >
              {t(`Theme.${value}`, label)}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}
