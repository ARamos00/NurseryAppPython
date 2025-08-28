import React, { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import * as api from '../api/auth'
import { useAuth } from '../auth/AuthContext'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const nav = useNavigate()
  const loc = useLocation()
  const { refresh } = useAuth()

  const next = useMemo(() => new URLSearchParams(loc.search).get('next') || '/', [loc.search])

  useEffect(() => {
    ;(async () => {
      try {
        await api.getCsrf()
      } catch {
        // Non-fatal; cookie may already exist
      }
    })()
  }, [])

  const onSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await api.login(username.trim(), password)
      await refresh()
      nav(next, { replace: true })
    } catch (err: any) {
      if (err?.status === 400 || err?.status === 401) setError('Invalid username or password.')
      else if (err?.status === 429) setError('Too many attempts. Please wait and try again.')
      else setError('Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [username, password, refresh, nav, next])

  return (
    <main style={{ maxWidth: 360, margin: '4rem auto', padding: '1rem' }}>
      <h1>Sign in</h1>
      <form onSubmit={onSubmit}>
        <label htmlFor="username">Username</label>
        <input
          id="username"
          name="username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          disabled={loading}
          required
        />
        <label htmlFor="password" style={{ display: 'block', marginTop: 8 }}>Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={loading}
          required
          onKeyDown={(e) => {
            if (e.key === 'Enter') (e.currentTarget.form as HTMLFormElement | null)?.requestSubmit()
          }}
        />
        {error && <p role="alert" style={{ color: 'crimson' }}>{error}</p>}
        <button type="submit" disabled={loading} style={{ marginTop: 12 }}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
