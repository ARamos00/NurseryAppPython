import React, { FormEvent, useCallback, useEffect, useState } from 'react'
import * as api from '../api/auth'
import { Link } from 'react-router-dom'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    void api.getCsrf() // prime CSRF; ignore errors
  }, [])

  const onSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await api.requestPasswordReset(email.trim())
      setSent(true) // always true (non-enumerating)
    } catch (err: any) {
      if (err?.status === 429) setError('Too many attempts; please wait a moment.')
      else setError('Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [email])

  return (
    <main style={{ maxWidth: 420, margin: '4rem auto', padding: '1rem' }}>
      <h1>Forgot your password?</h1>
      {sent ? (
        <>
          <p>We’ve sent password reset instructions if that email exists in our system.</p>
          <p style={{ marginTop: 12 }}>
            <Link to="/login">Return to sign in</Link>
          </p>
        </>
      ) : (
        <form onSubmit={onSubmit}>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
            required
          />
          {error && <p role="alert" style={{ color: 'crimson' }}>{error}</p>}
          <button type="submit" disabled={loading} style={{ marginTop: 12 }}>
            {loading ? 'Sending…' : 'Send reset link'}
          </button>
        </form>
      )}
    </main>
  )
}
