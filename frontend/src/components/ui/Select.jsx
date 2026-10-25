/**
 * Accessible select primitive.
 *
 * A native <select> cannot be driven reliably by the ported Playwright helpers,
 * which click a role="combobox" trigger and then a role="option". This keeps
 * that exact interaction while remaining keyboard accessible.
 */

import { useEffect, useRef, useState } from 'react'

/** @typedef {{value: string|number, label: string, disabled?: boolean}} SelectOption */

/**
 * @param {{
 *   id?: string,
 *   value: string|number,
 *   options: SelectOption[],
 *   onChange: (value: string) => void,
 *   placeholder?: string,
 *   disabled?: boolean,
 *   className?: string,
 *   testId?: string,
 *   ariaLabel?: string,
 * }} props
 */
export function Select({
  id,
  value,
  options,
  onChange,
  placeholder = 'Select…',
  disabled = false,
  className = '',
  testId,
  ariaLabel,
}) {
  const [open, setOpen] = useState(false)
  const container = useRef(/** @type {HTMLDivElement|null} */ (null))
  const selected = options.find((option) => String(option.value) === String(value))

  useEffect(() => {
    if (!open) return undefined
    /** @param {MouseEvent} event */
    const onPointerDown = (event) => {
      if (
        container.current &&
        event.target instanceof Node &&
        !container.current.contains(event.target)
      ) {
        setOpen(false)
      }
    }
    /** @param {KeyboardEvent} event */
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div ref={container} className={`relative ${className}`}>
      <button
        id={id}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        data-testid={testId}
        disabled={disabled}
        className="flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-card px-3 py-1 text-left text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        onClick={() => setOpen((current) => !current)}
      >
        <span className={selected ? 'truncate' : 'truncate text-muted-foreground'}>
          {selected ? selected.label : placeholder}
        </span>
        <span aria-hidden="true" className="text-xs text-muted-foreground">
          ▾
        </span>
      </button>
      {open ? (
        <div
          role="listbox"
          className="absolute z-40 mt-1 max-h-64 w-full overflow-auto rounded-md border border-border bg-popover p-1 text-sm shadow-lg"
        >
          {options.map((option) => {
            const active = String(option.value) === String(value)
            return (
              <button
                key={String(option.value)}
                type="button"
                role="option"
                aria-selected={active}
                disabled={option.disabled}
                className={`block w-full rounded px-2 py-1.5 text-left hover:bg-accent disabled:opacity-40 ${
                  active ? 'font-medium text-primary' : ''
                }`}
                onClick={() => {
                  setOpen(false)
                  onChange(String(option.value))
                }}
              >
                {option.label}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
