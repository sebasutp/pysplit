/** Text input and textarea primitives. */

/**
 * @param {React.ComponentProps<'input'>} props
 */
export function Input({ className = '', ...props }) {
  return (
    <input
      className={`flex h-9 w-full rounded-md border border-input bg-card px-3 py-1 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...props}
    />
  )
}

/**
 * @param {React.ComponentProps<'textarea'>} props
 */
export function Textarea({ className = '', ...props }) {
  return (
    <textarea
      className={`flex min-h-[60px] w-full rounded-md border border-input bg-card px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...props}
    />
  )
}
