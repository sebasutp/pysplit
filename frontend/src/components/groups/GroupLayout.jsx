/** Shared group shell: header, access recording and the active-user prompt. */

import { useEffect, useState } from 'react'
import { Outlet, useOutletContext, useParams } from 'react-router-dom'

import { useActiveUser } from '../../hooks/useActiveUser'
import { useAuth } from '../../hooks/useAuth'
import { useGroup } from '../../hooks/useGroup'
import { repository } from '../../services/repository'
import {
  clearPendingActiveUser,
  getPendingActiveUser,
  hasActiveUserKey,
  hasPendingActiveUser,
  saveRecentGroup,
} from '../../utils/recent-groups'
import { ErrorState, LoadingState } from '../common/States'
import { ActiveUserDialog } from './ActiveUserDialog'
import { GroupHeader } from './GroupHeader'

/** @param {unknown} name */
function normalizeName(name) {
  if (typeof name !== 'string') return ''
  return name.normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase()
}

export function GroupLayout() {
  const { groupId } = useParams()
  const { group, details, loading, error, reload } = useGroup(groupId)
  const { user } = useAuth()
  const { activeUserId, setActiveUserId } = useActiveUser(groupId || '')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [pendingResolvedFor, setPendingResolvedFor] = useState(
    /** @type {string|null} */ (null),
  )

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
    if (!group || pendingResolvedFor === group.id) return
    if (hasPendingActiveUser()) {
      const pending = getPendingActiveUser()
      if (pending) {
        const match = group.participants?.find(
          (/** @type {any} */ participant) => participant.name === pending,
        )
        if (match) setActiveUserId(match.id)
      }
      clearPendingActiveUser()
      setDialogOpen(false)
    } else if (!hasActiveUserKey(group.id)) {
      setDialogOpen(true)
    }
    setPendingResolvedFor(group.id)
  }, [group, pendingResolvedFor, setActiveUserId])

  // Preselect the participant that matches the signed-in account name. The
  // dialog still opens so the choice is explicit, and an existing active user
  // (or the explicit "nobody" answer) always wins over this suggestion.
  const accountName = normalizeName(user?.name)
  const accountParticipant = accountName
    ? group?.participants?.find(
        (/** @type {any} */ participant) => normalizeName(participant.name) === accountName,
      )
    : null

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
        initialValue={activeUserId ?? accountParticipant?.id ?? null}
        onOpenChange={setDialogOpen}
        onSave={(participantId) => {
          setActiveUserId(participantId)
          clearPendingActiveUser()
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
