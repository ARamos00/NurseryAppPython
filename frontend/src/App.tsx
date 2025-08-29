import React, { useCallback } from 'react'
import { BrowserRouter, Route, Routes, Navigate, Link, useNavigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { RequireAuth } from './auth/RequireAuth'

// Pages
import Home from './pages/Home'
import LoginPage from './pages/Login'
import RegisterPage from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import PasswordChangePage from './pages/PasswordChange'

// Minimal app layout with account section; keep it simple and framework-agnostic.
function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const nav = useNavigate()

  const onLogout = useCallback(async () => {
    try {
      await logout()
    } finally {
      nav('/login', { replace: true })
    }
  }, [logout, nav])

  return (
    <div>
      <header
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.75rem 1rem',
          borderBottom: '1px solid #e5e7eb',
        }}
      >
        <nav aria-label="Primary" style={{ display: 'flex', gap: 16 }}>
          <Link to="/" style={{ textDecoration: 'none', fontWeight: 600 }}>
            Nursery Tracker
          </Link>
          {/* Add more app links here as you build features */}
          <Link to="/settings/password">Password</Link>
        </nav>
        <div>
          {user && (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <span title={user.email} style={{ fontSize: 14, color: '#374151' }} aria-live="polite">
                {user.username}
              </span>
              <button type="button" onClick={onLogout} aria-label="Log out">
                Log out
              </button>
            </div>
          )}
        </div>
      </header>
      {children}
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <Routes>
          {/* Public auth routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />

          {/* Protected application routes */}
          <Route
            path="/"
            element={
              <RequireAuth>
                <AppLayout>
                  <Home />
                </AppLayout>
              </RequireAuth>
            }
          />
          <Route
            path="/settings/password"
            element={
              <RequireAuth>
                <AppLayout>
                  <PasswordChangePage />
                </AppLayout>
              </RequireAuth>
            }
          />

          {/* Catch-all: send unknown routes to root; RequireAuth will gate if needed */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
