/**
 * Labelled form field wrapper used by the group and expense forms.
 */

/** @param {{label: string, htmlFor?: string, description?: string, error?: string, className?: string, children: React.ReactNode}} props */
export function FormField({ label, htmlFor, description, error, className = '', children }) {
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
      {error ? (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  )
}
