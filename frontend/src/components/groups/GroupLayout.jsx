/** Shared group shell: header, access recording and the active-user prompt. */

import { useEffect, useState } from 'react'
import { Outlet, useOutletContext, useParams } from 'react-router-dom'

import { useActiveUser } from '../../hooks/useActiveUser'
import { useGroup } from '../../hooks/useGroup'
import { repository } from '../../services/repository'
import {
  hasActiveUserKey,
  hasPendingActiveUser,
  saveRecentGroup,
  setPendingActiveUser,
} from '../../utils/recent-groups'
import { ErrorState, LoadingState } from '../common/States'
import { ActiveUserDialog } from './ActiveUserDialog'
import { GroupHeader } from './GroupHeader'

export function GroupLayout() {
  const { groupId } = useParams()
  const { group, details, loading, error, reload } = useGroup(groupId)
  const { activeUserId, setActiveUserId } = useActiveUser(groupId || '')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [pendingResolved, setPendingResolved] = useState(false)

  // Persist the group in the recent list and record the visit for account sync.
  useEffect(() => {
    if (!group) return
    saveRecentGroup({ id: group.id, name: group.name })
    const controller = new AbortController()
    repository.groups
      .recordAccess(group.id, { signal: controller.signal })
      .catch(() => {
        // Guest links have no account; the local recent list is enough.
      })
    return () => controller.abort()
  }, [group])

  // Apply `newGroup-activeUser` once, then decide whether to ask.
  useEffect(() => {
    if (!group || pendingResolved) return
    if (hasPendingActiveUser()) {
      const pending = localStorage.getItem('newGroup-activeUser')
      if (pending && pending !== 'None') {
        const match = group.participants?.find(
          (/** @type {any} */ participant) => participant.name === pending,
        )
        if (match) setActiveUserId(match.id)
      }
      setDialogOpen(false)
    } else if (!hasActiveUserKey(group.id)) {
      setDialogOpen(true)
    }
    setPendingResolved(true)
  }, [group, pendingResolved, setActiveUserId])

  if (loading && !group) return <LoadingState />
  if (error) {
    return <ErrorState detail={error.detail || error.message} onRetry={() => void reload()} />
  }
  if (!group) {
    return (
      <ErrorState
        title="This group does not exist."
        detail="Check the URL or ask for a new invitation link."
      />
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <GroupHeader group={group} />
      <Outlet context={{ group, details, activeUserId, reloadGroup: reload }} />
      <ActiveUserDialog
        open={dialogOpen}
        participants={group.participants || []}
        initialValue={activeUserId}
        onOpenChange={setDialogOpen}
        onSave={(participantId) => {
          setActiveUserId(participantId)
          setPendingActiveUser(null)
          setDialogOpen(false)
        }}
      />
    </div>
  )
}

/**
 * Typed access to the layout's outlet context.
 *
 * @returns {{group: any, details: any, activeUserId: string|null, reloadGroup: () => Promise<void>}}
 */
export function useGroupContext() {
  return /** @type {any} */ (useOutletContext())
}
