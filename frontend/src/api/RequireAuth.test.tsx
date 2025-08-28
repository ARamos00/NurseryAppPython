import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, waitFor } from '@testing-library/react'
import { AuthProvider } from '../auth/AuthContext'
import { RequireAuth } from '../auth/RequireAuth'
import * as api from '../api/auth'

function AppUnderTest() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<div>Login</div>} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <div>Protected</div>
            </RequireAuth>
          }
        />
      </Routes>
    </AuthProvider>
  )
}

describe('RequireAuth', () => {
  afterEach(() => vi.restoreAllMocks())

  it('redirects to /login on 401', async () => {
    vi.spyOn(api, 'me').mockRejectedValueOnce(Object.assign(new Error('no'), { status: 401 }))
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppUnderTest />
      </MemoryRouter>
    )
    await waitFor(() => expect(screen.queryByText('Protected')).toBeNull())
  })

  it('renders children when authenticated', async () => {
    vi.spyOn(api, 'me').mockResolvedValueOnce({ id: 1, username: 'alice', email: '' })
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppUnderTest />
      </MemoryRouter>
    )
    await waitFor(() => expect(screen.getByText('Protected')).toBeInTheDocument())
  })
})

