/** /groups/create page with tier-aware approval states. */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { LoginDialog } from '../components/auth/LoginDialog'
import { LoadingState } from '../components/common/States'
import { CreateGroup } from '../components/groups/GroupForm'
import { Alert, AlertDescription, AlertTitle } from '../components/ui/Feedback'
import { buttonVariants } from '../components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card'
import { useAuth } from '../hooks/useAuth'

export function CreateGroupPage() {
  const { t } = useTranslation()
  const { user, loading, canCreateGroups } = useAuth()
  const [loginOpen, setLoginOpen] = useState(false)

  if (loading) return <LoadingState />

  if (!user) {
    return (
      <div className="mx-auto my-8 max-w-md">
        <Card className="border-2 border-dashed">
          <CardHeader className="text-center">
            <CardTitle className="text-xl">
              {t('CreateGroup.authRequiredTitle', 'Authentication Required')}
            </CardTitle>
            <CardDescription>
              {t(
                'CreateGroup.authRequiredDescription',
                'To create new expense groups, please sign in with an external account. Invited group participants will still be able to join friction-free via your group link without signing in.',
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <button
              type="button"
              className={`${buttonVariants({ variant: 'default' })} w-full`}
              onClick={() => setLoginOpen(true)}
            >
              {t('CreateGroup.signIn', 'Sign in to Create Group')}
            </button>
            <LoginDialog open={loginOpen} onOpenChange={setLoginOpen} />
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!canCreateGroups) {
    return (
      <div className="mx-auto my-8 max-w-xl">
        <Alert variant="warning">
          <AlertTitle>
            {t('CreateGroup.approvalTitle', 'Group Creation Requires Approval')}
          </AlertTitle>
          <AlertDescription className="mt-2 space-y-3">
            <p>
              {t(
                'CreateGroup.approvalDescription',
                'Your account is currently in the Sync User tier. You can participate in any groups shared with you and sync them across all your devices.',
              )}
            </p>
            <p>
              {t(
                'CreateGroup.approvalContact',
                'Creating new expense groups requires authorization from an administrator. Please contact your instance administrator to promote your account to the Group Creator tier.',
              )}
            </p>
            <Link to="/groups" className={buttonVariants({ variant: 'outline', size: 'sm' })}>
              {t('CreateGroup.returnToGroups', 'Return to My Groups')}
            </Link>
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return <CreateGroup />
}
