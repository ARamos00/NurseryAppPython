import React, { FormEvent, useCallback, useEffect, useState } from 'react'
import * as api from '../api/auth'
import { useAuth } from '../auth/AuthContext'

export default function PasswordChangePage() {
  const { user } = useAuth()
  const [oldPassword, setOld] = useState('')
  const [new1, setNew1] = useState('')
  const [new2, setNew2] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    ;(async () => {
      try {
        await api.getCsrf()
      } catch { /* ignore */ }
    })()
  }, [])

  const onSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setMsg(null)
    setError(null)
    try {
      await api.passwordChange(oldPassword, new1, new2)
      setMsg('Password updated successfully.')
      setOld('')
      setNew1('')
      setNew2('')
    } catch (err: any) {
      if (err?.status === 400) setError('Please check your current password and ensure the new passwords match policy.')
      else if (err?.status === 401) setError('You are not signed in.')
      else if (err?.status === 429) setError('Too many attempts. Please wait and try again.')
      else setError('Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [oldPassword, new1, new2])

  return (
    <main style={{ maxWidth: 420, margin: '4rem auto', padding: '1rem' }}>
      <h1>Change password</h1>
      <p style={{ marginTop: 4 }}>Signed in as <strong>{user?.username}</strong></p>
      <form onSubmit={onSubmit} noValidate>
        <label htmlFor="old">Current password</label>
        <input id="old" type="password" value={oldPassword} onChange={(e) => setOld(e.target.value)} required disabled={loading} />

        <label htmlFor="new1" style={{ display: 'block', marginTop: 8 }}>New password</label>
        <input id="new1" type="password" value={new1} onChange={(e) => setNew1(e.target.value)} required disabled={loading} />

        <label htmlFor="new2" style={{ display: 'block', marginTop: 8 }}>Confirm new password</label>
        <input id="new2" type="password" value={new2} onChange={(e) => setNew2(e.target.value)} required disabled={loading} />

        {msg && <p role="status" style={{ color: 'green' }}>{msg}</p>}
        {error && <p role="alert" style={{ color: 'crimson' }}>{error}</p>}

        <button type="submit" disabled={loading} style={{ marginTop: 12 }}>
          {loading ? 'Saving…' : 'Save'}
        </button>
      </form>
    </main>
  )
}
