/** Deep-link placeholders for routes implemented in later stages. */

import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { buttonVariants } from '../components/ui/Button'

/**
 * @param {{title: string, description: string}} props
 */
export function PlaceholderPage({ title, description }) {
  const { t } = useTranslation()
  return (
    <div className="rounded-lg border border-dashed border-border p-8 text-center">
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{description}</p>
      <Link to="/groups" className={`${buttonVariants({ variant: 'outline' })} mt-4`}>
        {t('Groups.myGroups', 'My groups')}
      </Link>
    </div>
  )
}
