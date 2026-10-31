/**
 * Active participant per group.
 *
 * The storage key is the reference `<groupId>-activeUser`; Stage 9C mirrors it
 * into Dexie for backup/migration, while this hook still reads the legacy key.
 * Components subscribe to a window event so every mounted card reacts
 * immediately to the dialog.
 */

import { useCallback, useEffect, useState } from 'react'

import { getActiveUser, setActiveUser as persistActiveUser } from '../utils/recent-groups'

const EVENT = 'pysplit-active-user'

/**
 * @param {string} groupId
 * @returns {{activeUserId: string|null, setActiveUserId: (id: string|null) => void}}
 */
export function useActiveUser(groupId) {
  const [activeUserId, setState] = useState(() => getActiveUser(groupId))

  useEffect(() => {
    setState(getActiveUser(groupId))
    /** @param {Event} event */
    const onChange = (event) => {
      if (event instanceof CustomEvent && event.detail?.groupId === groupId) {
        setState(getActiveUser(groupId))
      }
    }
    window.addEventListener(EVENT, onChange)
    window.addEventListener('storage', onChange)
    return () => {
      window.removeEventListener(EVENT, onChange)
      window.removeEventListener('storage', onChange)
    }
  }, [groupId])

  const setActiveUserId = useCallback(
    /** @param {string|null} id */
    (id) => {
      persistActiveUser(groupId, id)
      setState(getActiveUser(groupId))
      window.dispatchEvent(new CustomEvent(EVENT, { detail: { groupId } }))
    },
    [groupId],
  )

  return { activeUserId, setActiveUserId }
}
