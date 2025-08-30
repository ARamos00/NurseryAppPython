import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import LogoutButton from '../auth/LogoutButton'

/**
 * App-wide top navigation bar.
 * Kept intentionally minimal; styling can be centralized later.
 */
export default function NavBar() {
  const { user } = useAuth()

  return (
    <header
      role="banner"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.75rem 1rem',
        borderBottom: '1px solid #e5e7eb',
        background: '#ffffff',
      }}
    >
      <nav aria-label="Primary" style={{ display: 'flex', gap: 16 }}>
        <Link to="/" style={{ textDecoration: 'none', fontWeight: 600 }}>
          Nursery Tracker
        </Link>
        <Link to="/settings/password">Password</Link>
      </nav>

      {user && (
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <span title={user.email} style={{ fontSize: 14, color: '#374151' }} aria-live="polite">
            {user.username}
          </span>
          <LogoutButton />
        </div>
      )}
    </header>
  )
}
