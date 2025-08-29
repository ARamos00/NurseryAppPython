import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import * as api from '../api/auth'
import { useLocation } from 'react-router-dom'

type AuthCtx = {
  user: api.User | null
  hydrated: boolean
  refresh: () => Promise<void>
  logout: () => Promise<void>
}

const Ctx = createContext<AuthCtx | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<api.User | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const loc = useLocation()

  const refresh = useCallback(async () => {
    try {
      const u = await api.me()
      setUser(u)
    } catch (e: any) {
      if (e?.status === 401 || e?.status === 403) setUser(null)
      else throw e
    } finally {
      setHydrated(true)
    }
  }, [])

  const doLogout = useCallback(async () => {
    try { await api.getCsrf() } catch {}
    await api.logout()
    setUser(null)
  }, [])

  const isPublicAuthRoute =
    loc.pathname === '/login' ||
    loc.pathname === '/register' ||
    loc.pathname === '/forgot-password' ||
    loc.pathname === '/reset-password'

  useEffect(() => {
    if (!hydrated && !isPublicAuthRoute) {
      void refresh()
    }
  }, [hydrated, isPublicAuthRoute, refresh])

  const value = useMemo<AuthCtx>(() => ({ user, hydrated, refresh, logout: doLogout }), [user, hydrated, refresh, doLogout])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be used within <AuthProvider>')
  return v
}
