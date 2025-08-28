import React, { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './AuthContext'

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, hydrated } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()

  useEffect(() => {
    if (hydrated && !user) {
      const next = encodeURIComponent(loc.pathname + loc.search)
      nav(`/login?next=${next}`, { replace: true })
    }
  }, [hydrated, user, loc, nav])

  if (!hydrated) return <div aria-busy="true">Loading…</div>
  if (!user) return null
  return <>{children}</>
}
