/** /groups/:groupId/information */

import { useTranslation } from 'react-i18next'

import { useGroupContext } from '../../components/groups/GroupLayout'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/Card'

export function InformationPage() {
  const { group } = useGroupContext()
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('Information.title', 'Information')}</CardTitle>
        <CardDescription>
          {t(
            'Information.description',
            'Use this place to add any information that can be relevant to the group participants.',
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {group.information ? (
          <p className="whitespace-pre-wrap text-sm">{group.information}</p>
        ) : (
          <p className="text-sm text-muted-foreground">
            {t('Information.empty', 'No group information yet.')}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
