/** /admin — metrics, users, tiers and groups. */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { useAuth } from '../hooks/useAuth'
import { useToast } from '../hooks/useToast'
import { repository } from '../services/repository'
import { ErrorState, LoadingState } from '../components/common/States'
import { Button } from '../components/ui/Button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card'
import { Alert, AlertDescription, AlertTitle, Badge } from '../components/ui/Feedback'
import { FormField } from '../components/ui/Form'
import { Input } from '../components/ui/Input'
import { Select } from '../components/ui/Select'

const TIERS = [
  { value: 'sync_users', label: 'Sync User' },
  { value: 'group_creators', label: 'Group Creator' },
  { value: 'admin', label: 'Admin' },
]

export function AdminPage() {
  const { t } = useTranslation()
  const { user, loading: authLoading, isAdmin } = useAuth()
  const { toast } = useToast()
  const [metrics, setMetrics] = useState(/** @type {any|null} */ (null))
  const [users, setUsers] = useState(/** @type {any[]} */ ([]))
  const [groups, setGroups] = useState(/** @type {any[]} */ ([]))
  const [query, setQuery] = useState('')
  const [groupQuery, setGroupQuery] = useState('')
  const [email, setEmail] = useState('')
  const [tier, setTier] = useState('group_creators')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(/** @type {any} */ (null))
  const [nonce, setNonce] = useState(0)

  const reload = useCallback(() => setNonce((value) => value + 1), [])

  useEffect(() => {
    if (!isAdmin) return undefined
    const controller = new AbortController()
    setLoading(true)
    Promise.all([
      repository.admin.metrics({ signal: controller.signal }),
      repository.admin.users.list({ q: query, limit: 20 }, { signal: controller.signal }),
      repository.admin.groups.list({ q: groupQuery, limit: 20 }, { signal: controller.signal }),
    ])
      .then(([metricsPayload, usersPayload, groupsPayload]) => {
        setMetrics(metricsPayload)
        setUsers(usersPayload?.items || [])
        setGroups(groupsPayload?.items || [])
        setError(null)
      })
      .catch((caught) => {
        if (caught && typeof caught === 'object' && caught.code === 'aborted') return
        setError(caught)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [isAdmin, query, groupQuery, nonce])

  if (authLoading) return <LoadingState />
  if (!user) {
    return (
      <Alert variant="warning">
        <AlertTitle>{t('Admin.signInTitle', 'Sign in required')}</AlertTitle>
        <AlertDescription>
          {t('Admin.signInDescription', 'The administration dashboard requires an admin account.')}
        </AlertDescription>
      </Alert>
    )
  }
  if (!isAdmin) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('Admin.accessDenied', 'Access Denied')}</AlertTitle>
        <AlertDescription>
          {t(
            'Admin.accessDeniedDescription',
            'The Administration Dashboard is restricted to users in the Administrator tier.',
          )}
        </AlertDescription>
        <Link to="/groups" className="mt-3 inline-block text-sm underline">
          {t('Admin.returnToGroups', 'Return to My Groups')}
        </Link>
      </Alert>
    )
  }

  if (loading && !metrics) return <LoadingState label={t('Admin.loading', 'Loading dashboard…')} />
  if (error) return <ErrorState detail={error.detail || error.message} onRetry={reload} />

  return (
    <section className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold">{t('Admin.title', 'Administration Dashboard')}</h1>
        <p className="text-sm text-muted-foreground">
          {t(
            'Admin.description',
            'Manage user roles, platform access permissions, and monitor system metrics.',
          )}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {[
          [t('Admin.totalGroups', 'Total Groups'), metrics?.total_groups ?? 0],
          [t('Admin.totalExpenses', 'Total Expenses'), metrics?.total_expenses ?? 0],
          [t('Admin.registeredUsers', 'Registered Users'), metrics?.total_users ?? 0],
        ].map(([label, value]) => (
          <Card key={String(label)}>
            <CardHeader>
              <CardDescription>{label}</CardDescription>
              <CardTitle className="text-2xl tabular-nums">{value}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t('Admin.userManagement', 'User Management & Permission Tiers')}</CardTitle>
          <CardDescription>
            {t('Admin.userTier', 'Tiers')}: sync_users · group_creators · admin
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end gap-2">
            <FormField label={t('Admin.searchUsers', 'Search users')} htmlFor="admin-user-search">
              <Input
                id="admin-user-search"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </FormField>
            <div className="flex-1" />
          </div>
          <ul className="flex flex-col divide-y divide-border" data-testid="admin-users">
            {users.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium">{item.name || item.email || item.id}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {item.email} · {item.groups_count} {t('Admin.groups', 'groups')}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={item.tier === 'admin' ? 'destructive' : 'secondary'}>
                    {item.tier}
                  </Badge>
                  <div className="w-40">
                    <Select
                      value={item.tier}
                      options={TIERS}
                      ariaLabel={`${t('Admin.tierFor', 'Tier for')} ${item.email || item.id}`}
                      onChange={(value) => {
                        void repository.admin.users
                          .setTier(item.id, value)
                          .then(() => {
                            toast({ title: t('Admin.tierUpdated', 'Tier updated') })
                            reload()
                          })
                          .catch((caught) => {
                            toast({
                              title: t('Admin.tierError', 'Could not update the tier'),
                              description: caught instanceof Error ? caught.message : undefined,
                            })
                          })
                      }}
                    />
                  </div>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => {
                      void repository.admin.users
                        .remove(item.id)
                        .then(() => {
                          toast({ title: t('Admin.userDeleted', 'User deleted') })
                          reload()
                        })
                        .catch(() => toast({ title: t('Admin.deleteError', 'Could not delete the user') }))
                    }}
                  >
                    {t('Admin.delete', 'Delete')}
                  </Button>
                </div>
              </li>
            ))}
          </ul>

          <div className="rounded-md border border-border p-3">
            <h3 className="mb-2 text-sm font-semibold">
              {t('Admin.preauthorize', 'Pre-authorize a user')}
            </h3>
            <div className="flex flex-wrap items-end gap-2">
              <FormField label={t('Admin.email', 'Email')} htmlFor="admin-email">
                <Input
                  id="admin-email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </FormField>
              <div className="w-44">
                <label className="mb-1 block text-sm font-medium" htmlFor="admin-tier">
                  {t('Admin.tier', 'Tier')}
                </label>
                <Select id="admin-tier" value={tier} options={TIERS} onChange={setTier} />
              </div>
              <Button
                onClick={() => {
                  void repository.admin.users
                    .preauthorize({ email, tier })
                    .then(() => {
                      setEmail('')
                      toast({ title: t('Admin.preauthorized', 'User pre-authorized') })
                      reload()
                    })
                    .catch((caught) => {
                      toast({
                        title: t('Admin.preauthorizeError', 'Could not pre-authorize the user'),
                        description: caught instanceof Error ? caught.message : undefined,
                      })
                    })
                }}
                disabled={!email.trim()}
              >
                {t('Admin.preauthorizeAction', 'Pre-authorize')}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('Admin.groupManagement', 'Groups')}</CardTitle>
          <CardDescription>{t('Admin.groupManagementDescription', 'Delete groups and inspect usage.')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Input
            type="search"
            value={groupQuery}
            onChange={(event) => setGroupQuery(event.target.value)}
            aria-label={t('Admin.searchGroups', 'Search groups')}
          />
          <ul className="flex flex-col divide-y divide-border" data-testid="admin-groups">
            {groups.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <div>
                  <p className="font-medium">{item.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {item.participants_count} {t('Admin.participants', 'participants')} ·{' '}
                    {item.expenses_count} {t('Admin.expenses', 'expenses')}
                  </p>
                </div>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() =>
                    repository.admin.groups
                      .remove(item.id)
                      .then(() => {
                        toast({ title: t('Admin.groupDeleted', 'Group deleted') })
                        reload()
                      })
                      .catch(() => toast({ title: t('Admin.deleteError', 'Could not delete the group') }))
                  }
                >
                  {t('Admin.delete', 'Delete')}
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </section>
  )
}
