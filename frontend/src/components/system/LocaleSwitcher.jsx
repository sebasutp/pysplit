/** Language selector. */

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { getLocale, localeLabel, setLocale, SUPPORTED_LOCALES } from '../../services/i18n'
import { buttonVariants } from '../ui/Button'

export function LocaleSwitcher() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [locale, setCurrentLocale] = useState(getLocale)
  const container = useRef(/** @type {HTMLDivElement | null} */ (null))

  useEffect(() => {
    if (!open) return undefined
    /** @param {MouseEvent} event */
    const onClick = (event) => {
      if (container.current && event.target instanceof Node && !container.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  return (
    <div ref={container} className="relative">
      <button
        type="button"
        className={buttonVariants({ variant: 'ghost', size: 'sm' })}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('Header.language', 'Language')}
        onClick={() => setOpen((value) => !value)}
      >
        {localeLabel(locale)}
      </button>
      {open ? (
        <ul
          role="listbox"
          className="absolute right-0 top-9 z-40 max-h-72 w-48 overflow-auto rounded-md border border-border bg-popover p-1 text-sm shadow-lg"
        >
          {SUPPORTED_LOCALES.map((option) => (
            <li key={option}>
              <button
                type="button"
                role="option"
                aria-selected={option === locale}
                className="w-full rounded px-2 py-1.5 text-left hover:bg-accent"
                onClick={async () => {
                  const next = await setLocale(option)
                  setCurrentLocale(next)
                  setOpen(false)
                }}
              >
                {localeLabel(option)} <span className="text-xs text-muted-foreground">{option}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
