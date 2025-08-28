import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import * as api from '../api/auth'

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

  const refresh = useCallback(async () => {
    try {
      const u = await api.me()
      setUser(u)
    } catch (e: any) {
      // Treat 401 and 403 as "not authenticated"
      if (e?.status === 401 || e?.status === 403) {
        setUser(null)
      } else {
        throw e
      }
    } finally {
      setHydrated(true)
    }
  }, [])

  const doLogout = useCallback(async () => {
    await api.logout()
    setUser(null)
  }, [])

  useEffect(() => {
    // Single initial hydration fetch
    refresh().catch(() => void 0)
  }, [refresh])

  return (
    <Ctx.Provider value={{ user, hydrated, refresh, logout: doLogout }}>
      {children}
    </Ctx.Provider>
  )
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be used within <AuthProvider>')
  return v
}
