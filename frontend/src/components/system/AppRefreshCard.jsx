/** Manual hard-refresh control for the first page. */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { forceRefreshApp } from '../../services/pwa'
import { Button } from '../ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'

export function AppRefreshCard() {
  const { t } = useTranslation()
  const [refreshing, setRefreshing] = useState(false)

  async function refresh() {
    setRefreshing(true)
    try {
      await forceRefreshApp()
    } catch {
      // forceRefreshApp already falls back to a reload; keep the button usable.
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <Card data-testid="app-refresh-card">
      <CardHeader>
        <CardTitle className="text-base">{t('Pwa.refreshApp', 'Refresh app')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {t(
            'Pwa.refreshAppHint',
            'Clear cached files and reload the latest version. Your saved data stays on this device.',
          )}
        </p>
        <Button variant="outline" disabled={refreshing} onClick={() => void refresh()}>
          {refreshing ? t('Pwa.updating', 'Updating…') : t('Pwa.refreshApp', 'Refresh app')}
        </Button>
      </CardContent>
    </Card>
  )
}
