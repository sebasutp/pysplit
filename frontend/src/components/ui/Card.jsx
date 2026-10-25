/** Card layout primitives. */

/**
 * @param {React.ComponentProps<'div'>} props
 */
export function Card({ className = '', ...props }) {
  return <div className={`rounded-lg border border-border bg-card text-card-foreground shadow-sm ${className}`} {...props} />
}

/** @param {React.ComponentProps<'div'>} props */
export function CardHeader({ className = '', ...props }) {
  return <div className={`flex flex-col gap-1.5 p-5 ${className}`} {...props} />
}

/** @param {React.ComponentProps<'h3'>} props */
export function CardTitle({ className = '', ...props }) {
  return <h3 className={`font-semibold leading-none tracking-tight ${className}`} {...props} />
}

/** @param {React.ComponentProps<'p'>} props */
export function CardDescription({ className = '', ...props }) {
  return <p className={`text-sm text-muted-foreground ${className}`} {...props} />
}

/** @param {React.ComponentProps<'div'>} props */
export function CardContent({ className = '', ...props }) {
  return <div className={`p-5 pt-0 ${className}`} {...props} />
}

/** @param {React.ComponentProps<'div'>} props */
export function CardFooter({ className = '', ...props }) {
  return <div className={`flex items-center p-5 pt-0 ${className}`} {...props} />
}
