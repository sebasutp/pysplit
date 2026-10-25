/** Toast context and renderer. */

import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'

/** @typedef {{id: number, title: string, description?: string}} Toast */

const ToastContext = createContext(
  /** @type {{toast: (input: {title: string, description?: string}) => void, dismiss: (id: number) => void} | null} */ (null),
)

/** @param {{children: React.ReactNode}} props */
export function ToastProvider({ children }) {
  /** @type {[Toast[], import('react').Dispatch<import('react').SetStateAction<Toast[]>>]} */
  const [toasts, setToasts] = useState(/** @type {Toast[]} */ ([]))
  const counter = useRef(0)

  const toast = useCallback(
    /** @param {{title: string, description?: string}} input */
    (input) => {
    counter.current += 1
    const id = counter.current
    setToasts((previous) => [...previous, { id, ...input }])
    window.setTimeout(() => {
      setToasts((previous) => previous.filter((item) => item.id !== id))
      }, 5000)
    },
    [],
  )

  const dismiss = useCallback(
    /** @param {number} id */
    (id) => {
      setToasts((previous) => previous.filter((item) => item.id !== id))
    },
    [],
  )

  const value = useMemo(() => ({ toast, dismiss }), [toast, dismiss])
  return (
    <ToastContext.Provider value={value}>
      {children}
      <Toaster toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside ToastProvider')
  return context
}

/** @param {{toasts: Toast[], dismiss: (id: number) => void}} props */
function Toaster({ toasts, dismiss }) {
  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-full max-w-sm flex-col gap-2"
    >
      {toasts.map((item) => (
        <div
          key={item.id}
          role="status"
          className="pointer-events-auto rounded-md border border-border bg-card p-4 shadow-lg"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="font-medium">{item.title}</p>
              {item.description ? (
                <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
              ) : null}
            </div>
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => dismiss(item.id)}
              aria-label="Dismiss notification"
            >
              ✕
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

export { ToastContext }
