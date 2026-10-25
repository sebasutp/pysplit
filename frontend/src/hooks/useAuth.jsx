/**
 * Authentication state for the shell.
 *
 * Components consume this hook; only this hook talks to repository.auth.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { repository } from '../services/repository'

/** @typedef {{id: string, name?: string|null, email?: string|null, image?: string|null, tier: string}} User */

/** @type {React.Context<any>} */
const AuthContext = createContext(null)

/** @param {{children: React.ReactNode}} props */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(/** @type {User | null} */ (null))
  const [providers, setProviders] = useState(
    /** @type {{google: boolean, github: boolean}} */ ({ google: false, github: false }),
  )
  const [loading, setLoading] = useState(true)

  const load = useCallback(
    /** @param {AbortSignal} [signal] */
    async (signal) => {
    try {
      await repository.auth.refresh()
    } catch (error) {
      if (error && typeof error === 'object' && 'code' in error && error.code === 'aborted') {
        return
      }
    }

    try {
      const current = await repository.auth.me({ signal })
      setUser(/** @type {User | null} */ (current))
      setProviders(repository.auth.providers())
    } catch (error) {
      if (error && typeof error === 'object' && 'code' in error && error.code === 'aborted') {
        return
      }
        setUser(null)
      }
    },
    [],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal).finally(() => setLoading(false))
    return () => controller.abort()
  }, [load])

  const login = useCallback(
    /** @param {'google'|'github'} provider @param {string} [returnTo] */
    (provider, returnTo) => {
      repository.auth.startOAuth(provider, returnTo || '/groups')
    },
    [],
  )

  const logout = useCallback(async () => {
    try {
      await repository.auth.logout()
    } finally {
      setUser(null)
    }
  }, [])

  const refresh = useCallback(() => load(), [load])

  const value = useMemo(
    () => ({
      user,
      providers,
      loading,
      isAuthenticated: Boolean(user),
      canCreateGroups: Boolean(user && ['group_creators', 'admin'].includes(user.tier)),
      isAdmin: Boolean(user && user.tier === 'admin'),
      login,
      logout,
      refresh,
    }),
    [user, providers, loading, login, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
