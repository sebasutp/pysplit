/**
 * Button primitive with the small variant set the shell needs.
 */

const VARIANTS = {
  default: 'bg-primary text-primary-foreground hover:bg-primary/90',
  secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
  outline: 'border border-border bg-card text-foreground hover:bg-accent',
  ghost: 'text-foreground hover:bg-accent hover:text-accent-foreground',
  destructive: 'bg-destructive text-white hover:bg-destructive/90',
  link: 'text-primary underline-offset-4 hover:underline',
}

const SIZES = {
  default: 'h-9 px-4 py-2 text-sm',
  sm: 'h-8 px-3 text-xs',
  icon: 'h-9 w-9 p-0',
  lg: 'h-10 px-6 text-base',
}

/**
 * @param {{variant?: keyof typeof VARIANTS, size?: keyof typeof SIZES, className?: string}} [options]
 * @returns {string}
 */
export function buttonVariants(options = {}) {
  const variant = options.variant || 'default'
  const size = options.size || 'default'
  return [
    'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
    'disabled:pointer-events-none disabled:opacity-50',
    VARIANTS[variant],
    SIZES[size],
    options.className || '',
  ]
    .filter(Boolean)
    .join(' ')
}

/**
 * @param {React.ComponentProps<'button'> & {variant?: keyof typeof VARIANTS, size?: keyof typeof SIZES}} props
 */
export function Button({ variant = 'default', size = 'default', className = '', type = 'button', ...props }) {
  return <button type={type} className={buttonVariants({ variant, size, className })} {...props} />
}
