/**
 * Group-list data for the shell.
 *
 * Reads the reference localStorage lists, then asks the repository to sync and
 * return server details. Only this hook talks to repository.groups.
 */

import { useCallback, useEffect, useState } from 'react'

import { repository } from '../services/repository'
import {
  archiveGroup,
  deleteRecentGroup,
  getArchivedGroups,
  getRecentGroups,
  getStarredGroups,
  saveRecentGroup,
  starGroup,
  unarchiveGroup,
  unstarGroup,
} from '../utils/recent-groups'

/**
 * @typedef {{id: string, name: string}} RecentGroup
 * @typedef {{
 *   status: 'pending'|'complete',
 *   groups: RecentGroup[],
 *   starredGroups: string[],
 *   archivedGroups: string[],
 *   details: any[]
 * }} GroupsState
 */

/** @returns {GroupsState} */
function emptyState() {
  return {
    status: 'pending',
    groups: [],
    starredGroups: [],
    archivedGroups: [],
    details: [],
  }
}

export function useGroups() {
  const [state, setState] = useState(/** @type {GroupsState} */ (emptyState()))

  const load = useCallback(
    /** @param {AbortSignal} [signal] */
    async (signal) => {
    const localGroups = getRecentGroups()
    const localStarred = getStarredGroups()
    const localArchived = getArchivedGroups()
    setState((previous) => ({ ...previous, status: 'pending' }))

    try {
      const result = await repository.groups.sync(
        {
          groupIds: localGroups.map((group) => group.id),
          starredGroupIds: localStarred,
          archivedGroupIds: localArchived,
        },
        { signal },
      )
      const authenticated = Boolean(result?.is_authenticated ?? result?.isAuthenticated)
      const details = Array.isArray(result?.groups) ? result.groups : []

      if (authenticated) {
        for (const group of /** @type {any[]} */ (details)) {
          saveRecentGroup({ id: group.id, name: group.name })
          if (group.is_starred ?? group.isStarred) starGroup(group.id)
          else unstarGroup(group.id)
          if (group.is_archived ?? group.isArchived) archiveGroup(group.id)
          else unarchiveGroup(group.id)
        }
        setState({
          status: 'complete',
          groups: /** @type {any[]} */ (details).map((/** @type {any} */ group) => ({
            id: group.id,
            name: group.name,
          })),
          starredGroups: /** @type {any[]} */ (details)
            .filter((/** @type {any} */ group) => group.is_starred ?? group.isStarred)
            .map((/** @type {any} */ group) => group.id),
          archivedGroups: /** @type {any[]} */ (details)
            .filter((/** @type {any} */ group) => group.is_archived ?? group.isArchived)
            .map((/** @type {any} */ group) => group.id),
          details,
        })
        return
      }

      setState({
        status: 'complete',
        groups: localGroups,
        starredGroups: localStarred,
        archivedGroups: localArchived,
        details,
      })
    } catch {
      setState({
        status: 'complete',
        groups: localGroups,
        starredGroups: localStarred,
        archivedGroups: localArchived,
        details: [],
        })
      }
    },
    [],
  )

  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  const setStarred = useCallback(
    /** @param {string} groupId @param {boolean} value */
    async (groupId, value) => {
      if (value) {
        starGroup(groupId)
        unarchiveGroup(groupId)
      } else {
        unstarGroup(groupId)
      }
      setState((previous) => ({
        ...previous,
        starredGroups: value
          ? [...new Set([...previous.starredGroups, groupId])]
          : previous.starredGroups.filter((id) => id !== groupId),
        archivedGroups: value
          ? previous.archivedGroups.filter((id) => id !== groupId)
          : previous.archivedGroups,
      }))
      try {
        await repository.groups.setStarred(groupId, value)
      } catch {
        // Guests keep the local state; the server flag requires an account.
      }
    },
    [],
  )

  const setArchived = useCallback(
    /** @param {string} groupId @param {boolean} value */
    async (groupId, value) => {
      if (value) {
        archiveGroup(groupId)
        unstarGroup(groupId)
      } else {
        unarchiveGroup(groupId)
      }
      setState((previous) => ({
        ...previous,
        archivedGroups: value
          ? [...new Set([...previous.archivedGroups, groupId])]
          : previous.archivedGroups.filter((id) => id !== groupId),
        starredGroups: value
          ? previous.starredGroups.filter((id) => id !== groupId)
          : previous.starredGroups,
      }))
      try {
        await repository.groups.setArchived(groupId, value)
        if (value) await repository.groups.setStarred(groupId, false)
      } catch {
        // Guests keep the local state; the server flag requires an account.
      }
    },
    [],
  )

  const remove = useCallback(
    /** @param {string} groupId */
    async (groupId) => {
    deleteRecentGroup(groupId)
    setState((previous) => ({
      ...previous,
      groups: previous.groups.filter((group) => group.id !== groupId),
      starredGroups: previous.starredGroups.filter((id) => id !== groupId),
      archivedGroups: previous.archivedGroups.filter((id) => id !== groupId),
      details: previous.details.filter((group) => group.id !== groupId),
    }))
    try {
      await repository.groups.removeMembership(groupId)
    } catch {
      // Guest lists are local-only; removing the local entry is enough.
    }
  }, [])

  return { ...state, reload: load, setStarred, setArchived, remove }
}
