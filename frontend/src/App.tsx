import React from 'react'
import { BrowserRouter, Route, Routes, Navigate, Link } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { RequireAuth } from './auth/RequireAuth'

// Pages
import Home from './pages/Home'
import LoginPage from './pages/Login'
import RegisterPage from './pages/Register'
import ForgotPassword from './pages/ForgotPassword'
import ResetPassword from './pages/ResetPassword'
import PasswordChangePage from './pages/PasswordChange'
import LogoutButton from './auth/LogoutButton'

// Minimal app layout with account section
function AppLayout({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()

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
          <Link to="/settings/password">Password</Link>
        </nav>
        <div>
          {user && (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <span title={user.email} style={{ fontSize: 14, color: '#374151' }} aria-live="polite">
                {user.username}
              </span>
              <LogoutButton />
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

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
