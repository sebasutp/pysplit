/**
 * Placeholder used by the Stage 1 route shell. Feature stages replace these
 * with real screens; keeping them in one component guarantees the shell is
 * accessible and consistently styled while the API is built.
 *
 * @param {{ title: string, description?: string }} props
 */
export function PagePlaceholder({ title, description = 'This screen is scaffolded in a later stage.' }) {
  return (
    <section className="space-y-2">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="text-muted-foreground">{description}</p>
    </section>
  )
}
