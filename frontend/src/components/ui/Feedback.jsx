/** Small presentational primitives: alert, badge, skeleton. */

/** @param {React.ComponentProps<'div'> & {variant?: 'default'|'destructive'|'warning'}} props */
export function Alert({ className = '', variant = 'default', ...props }) {
  const tone =
    variant === 'destructive'
      ? 'border-destructive/40 bg-destructive/10 text-destructive'
      : variant === 'warning'
        ? 'border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-200'
        : 'border-border bg-card'
  return <div role="alert" className={`rounded-lg border p-4 ${tone} ${className}`} {...props} />
}

/** @param {React.ComponentProps<'h3'>} props */
export function AlertTitle({ className = '', ...props }) {
  return <h3 className={`font-semibold ${className}`} {...props} />
}

/** @param {React.ComponentProps<'div'>} props */
export function AlertDescription({ className = '', ...props }) {
  return <div className={`text-sm ${className}`} {...props} />
}

/** @param {React.ComponentProps<'span'> & {variant?: 'default'|'secondary'|'destructive'}} props */
export function Badge({ className = '', variant = 'default', ...props }) {
  const tone =
    variant === 'destructive'
      ? 'bg-destructive text-white'
      : variant === 'secondary'
        ? 'bg-secondary text-secondary-foreground'
        : 'bg-primary text-primary-foreground'
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tone} ${className}`}
      {...props}
    />
  )
}

/** @param {React.ComponentProps<'div'>} props */
export function Skeleton({ className = '', ...props }) {
  return <div className={`animate-pulse rounded-md bg-muted ${className}`} aria-hidden="true" {...props} />
}
