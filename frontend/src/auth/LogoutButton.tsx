import * as React from 'react'
import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, CircularProgress } from '@mui/material'
import LogoutIcon from '@mui/icons-material/Logout'
import { useAuth } from './AuthContext'
import * as api from '../api/auth'

type Props = {
  children?: React.ReactNode
  className?: string
  /** Optional styling controls if you want to override defaults at call sites */
  size?: 'small' | 'medium' | 'large'
  variant?: 'text' | 'outlined' | 'contained'
}

/**
 * LogoutButton — MUI version (preserves existing behavior)
 * Flow:
 *   1) Ensure CSRF cookie is fresh (unsafe POSTs require it)
 *   2) Call useAuth().logout()
 *   3) Navigate to /login in finally (always), then clear pending
 */
export default function LogoutButton({
  children = 'Log out',
  className,
  size = 'small',
  variant = 'outlined',
}: Props) {
  const { logout } = useAuth()
  const nav = useNavigate()
  const [pending, setPending] = useState(false)

  const onClick = useCallback(async () => {
    if (pending) return
    setPending(true)
    try {
      await api.getCsrf()
      await logout()
    } finally {
      // Preserve original semantics: always go to the login page after attempting logout
      nav('/login', { replace: true })
      setPending(false)
    }
  }, [logout, nav, pending])

  return (
    <Button
      type="button"
      onClick={onClick}
      disabled={pending}
      aria-busy={pending || undefined}
      aria-label="Log out"
      className={className}
      size={size}
      variant={variant}
      startIcon={!pending ? <LogoutIcon /> : undefined}
      sx={{ textTransform: 'none' }}
    >
      {pending ? (
        <>
          <CircularProgress size={16} sx={{ mr: 1 }} />
          Signing out…
        </>
      ) : (
        children
      )}
    </Button>
  )
}
