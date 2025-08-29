import React, { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import * as api from '../api/auth'
import { Link, useLocation } from 'react-router-dom'

export default function ResetPassword() {
  const loc = useLocation()
  const params = useMemo(() => new URLSearchParams(loc.search), [loc.search])
  const uid = params.get('uid') ?? ''
  const token = params.get('token') ?? ''
  const [p1, setP1] = useState('')
  const [p2, setP2] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    void api.getCsrf() // prime CSRF; ignore errors
  }, [])

  const onSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!uid || !token) {
      setError('The reset link is invalid. Please request a new one.')
      return
    }
    if (p1 !== p2) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    try {
      await api.resetPasswordConfirm({ uid, token, newPassword1: p1, newPassword2: p2 })
      setOk(true)
    } catch (err: any) {
      if (err?.status === 400) setError('Invalid or expired link, or password does not meet requirements.')
      else if (err?.status === 429) setError('Too many attempts; please wait a moment.')
      else setError('Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [uid, token, p1, p2])

  return (
    <main style={{ maxWidth: 420, margin: '4rem auto', padding: '1rem' }}>
      <h1>Reset your password</h1>
      {ok ? (
        <>
          <p>Your password has been reset.</p>
          <p style={{ marginTop: 12 }}>
            <Link to="/login">Go to sign in</Link>
          </p>
        </>
      ) : (
        <form onSubmit={onSubmit}>
          <label htmlFor="p1">New password</label>
          <input
            id="p1"
            name="new-password"
            type="password"
            autoComplete="new-password"
            value={p1}
            onChange={(e) => setP1(e.target.value)}
            disabled={loading}
            required
          />
          <label htmlFor="p2" style={{ display: 'block', marginTop: 8 }}>Confirm new password</label>
          <input
            id="p2"
            name="new-password-confirm"
            type="password"
            autoComplete="new-password"
            value={p2}
            onChange={(e) => setP2(e.target.value)}
            disabled={loading}
            required
          />
          {error && <p role="alert" style={{ color: 'crimson' }}>{error}</p>}
          <button type="submit" disabled={loading} style={{ marginTop: 12 }}>
            {loading ? 'Resetting…' : 'Reset password'}
          </button>
          <p style={{ marginTop: 12 }}>
            Don’t have a link? <Link to="/forgot-password">Request a new one</Link>
          </p>
        </form>
      )}
    </main>
  )
}
