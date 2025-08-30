import React, { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import * as api from '../api/auth'

type Props = { children?: React.ReactNode; className?: string }

export default function LogoutButton({ children = 'Log out', className }: Props) {
  const { logout } = useAuth()
  const nav = useNavigate()
  const [pending, setPending] = useState(false)

  const onClick = useCallback(async () => {
    if (pending) return
    setPending(true)
    try {
      // Ensure CSRF cookie is fresh before unsafe POST
      await api.getCsrf()
      await logout()
    } finally {
      setPending(false)
      nav('/login', { replace: true })
    }
  }, [logout, nav, pending])

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={pending}
      aria-busy={pending || undefined}
      className={className}
      aria-label="Log out"
    >
      {children}
    </button>
  )
}
