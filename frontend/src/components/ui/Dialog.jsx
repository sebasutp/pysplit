/**
 * Accessible modal primitive. It is deliberately small: focus trapping and
 * portal libraries are outside the agreed stack, so this keeps Escape,
 * backdrop dismissal and aria semantics explicit.
 */

import { useEffect, useId } from 'react'
import { createPortal } from 'react-dom'

/**
 * @param {{open: boolean, onOpenChange?: (open: boolean) => void, children: React.ReactNode}} props
 */
export function Dialog({ open, onOpenChange, children }) {
  useEffect(() => {
    if (!open) return undefined
    /** @param {KeyboardEvent} event */
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onOpenChange?.(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onOpenChange])

  if (!open) return null
  if (typeof document === 'undefined') return null
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Close dialog"
        className="absolute inset-0 bg-black/50"
        onClick={() => onOpenChange?.(false)}
      />
      {children}
    </div>,
    document.body,
  )
}

/**
 * @param {{children: React.ReactNode, className?: string, labelledBy?: string, describedBy?: string}} props
 */
export function DialogContent({ children, className = '', labelledBy, describedBy }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      className={`relative z-10 w-full max-w-md rounded-lg border border-border bg-card p-5 shadow-xl ${className}`}
    >
      {children}
    </div>
  )
}

/** @param {React.ComponentProps<'div'>} props */
export function DialogHeader({ className = '', ...props }) {
  return <div className={`flex flex-col gap-1.5 ${className}`} {...props} />
}

/** @param {{children: React.ReactNode, className?: string}} props */
export function DialogTitle({ children, className = '' }) {
  const id = useId()
  return (
    <h2 id={id} className={`text-lg font-semibold ${className}`}>
      {children}
    </h2>
  )
}

/** @param {React.ComponentProps<'p'>} props */
export function DialogDescription({ className = '', ...props }) {
  return <p className={`text-sm text-muted-foreground ${className}`} {...props} />
}
