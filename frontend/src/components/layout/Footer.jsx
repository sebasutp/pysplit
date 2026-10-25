/** Static footer. */

import { useTranslation } from 'react-i18next'

import { APP_NAME } from '../../services/config'

export function Footer() {
  const { t } = useTranslation()
  return (
    <footer className="mt-16 border-t border-border bg-muted/40 px-4 py-6 text-xs text-muted-foreground">
      <div className="mx-auto flex max-w-5xl flex-col gap-1 sm:flex-row sm:justify-between">
        <span>{APP_NAME}</span>
        <span>{t('Footer.madeIn', 'Made with ❤️ for sharing expenses.')}</span>
      </div>
    </footer>
  )
}
