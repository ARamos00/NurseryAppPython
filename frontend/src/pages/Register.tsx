import React, { FormEvent, useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as api from '../api/auth'
import { useAuth } from '../auth/AuthContext'

export default function RegisterPage() {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password1, setPassword1] = useState('')
  const [password2, setPassword2] = useState('')
  const [errors, setErrors] = useState<Record<string, string[]> | null>(null)
  const [nonFieldError, setNonFieldError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const nav = useNavigate()
  const { refresh } = useAuth()

  useEffect(() => {
    ;(async () => {
      try {
        await api.getCsrf()
      } catch {
        /* ignore */
      }
    })()
  }, [])

  const onSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setErrors(null)
    setNonFieldError(null)
    try {
      await api.register(username.trim(), email.trim(), password1, password2)
      // Auto-login enabled server-side; refresh context and go home
      await refresh()
      nav('/', { replace: true })
    } catch (err: any) {
      if (err?.status === 400) {
        // If server returned field errors, our http() will throw with status=400 and statusText;
        // try to refetch details (http() already parsed once, but we don't have the body here)
        // So we display a generic message and ask user to adjust; or you can extend http() to attach parsed json.
        setNonFieldError('Please correct the highlighted fields.')
      } else if (err?.status === 403) {
        setNonFieldError('Registration is currently disabled.')
      } else if (err?.status === 429) {
        setNonFieldError('Too many attempts. Please wait and try again.')
      } else {
        setNonFieldError('Something went wrong. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }, [username, email, password1, password2, refresh, nav])

  return (
    <main style={{ maxWidth: 420, margin: '4rem auto', padding: '1rem' }}>
      <h1>Create your account</h1>
      <form onSubmit={onSubmit} noValidate>
        <label htmlFor="username">Username</label>
        <input id="username" value={username} onChange={(e) => setUsername(e.target.value)} required disabled={loading} />

        <label htmlFor="email" style={{ display: 'block', marginTop: 8 }}>Email</label>
        <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required disabled={loading} />

        <label htmlFor="password1" style={{ display: 'block', marginTop: 8 }}>Password</label>
        <input id="password1" type="password" value={password1} onChange={(e) => setPassword1(e.target.value)} required disabled={loading} />

        <label htmlFor="password2" style={{ display: 'block', marginTop: 8 }}>Confirm password</label>
        <input id="password2" type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} required disabled={loading} />

        {nonFieldError && <p role="alert" style={{ color: 'crimson' }}>{nonFieldError}</p>}
        {/* For brevity, field-level error rendering omitted; you can extend http() to bubble JSON bodies and map here. */}

        <button type="submit" disabled={loading} style={{ marginTop: 12 }}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <p style={{ marginTop: 12 }}>
        Already have an account? <Link to="/login">Sign in</Link>
      </p>
    </main>
  )
}
