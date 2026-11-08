/**
 * Page-level loading, empty and error states with accessible announcements.
 */

import { useTranslation } from 'react-i18next'

/** @param {{label?: string}} props */
export function LoadingState({ label }) {
  const { t } = useTranslation()
  return (
    <div role="status" aria-live="polite" className="flex items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      <span>{label ?? t('Common.loading', 'Loading…')}</span>
    </div>
  )
}

/** @param {{title: string, description?: string, action?: React.ReactNode}} props */
export function EmptyState({ title, description, action }) {
  return (
    <div className="rounded-lg border border-dashed border-border p-8 text-center">
      <p className="font-medium">{title}</p>
      {description ? <p className="mt-2 text-sm text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}

/** @param {{title?: string, detail?: string, onRetry?: () => void}} props */
export function ErrorState({ title, detail, onRetry }) {
  const { t } = useTranslation()
  return (
    <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 p-5">
      <p className="font-medium text-destructive">
        {title ?? t('Common.error', 'Something went wrong')}
      </p>
      {detail ? <p className="mt-1 text-sm text-muted-foreground">{detail}</p> : null}
      {onRetry ? (
        <button
          type="button"
          className="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-accent"
          onClick={onRetry}
        >
          {t('Common.retry', 'Retry')}
        </button>
      ) : null}
    </div>
  )
}
