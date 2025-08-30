import React, { FormEvent, useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Container,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
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

  // Prime CSRF cookie; ignore if already present.
  useEffect(() => {
    void api.getCsrf().catch(() => {})
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
    <Container maxWidth="sm">
      <Box component="main" sx={{ mt: 8 }}>
        <Typography variant="h5" fontWeight={700} gutterBottom>
          Change password
        </Typography>
        <Typography sx={{ mb: 2 }}>
          Signed in as <strong>{user?.username}</strong>
        </Typography>

        {msg && (
          <Alert severity="success" sx={{ mb: 2 }} role="status">
            {msg}
          </Alert>
        )}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} role="alert">
            {error}
          </Alert>
        )}

        <Box component="form" onSubmit={onSubmit} noValidate>
          <Stack spacing={2}>
            <TextField
              id="old"
              label="Current password"
              type="password"
              value={oldPassword}
              onChange={(e) => setOld(e.target.value)}
              required
              disabled={loading}
              fullWidth
              autoFocus
            />
            <TextField
              id="new1"
              label="New password"
              type="password"
              value={new1}
              onChange={(e) => setNew1(e.target.value)}
              required
              disabled={loading}
              fullWidth
            />
            <TextField
              id="new2"
              label="Confirm new password"
              type="password"
              value={new2}
              onChange={(e) => setNew2(e.target.value)}
              required
              disabled={loading}
              fullWidth
            />
            <Button type="submit" variant="contained" disabled={loading}>
              {loading ? 'Saving…' : 'Save'}
            </Button>
          </Stack>
        </Box>
      </Box>
    </Container>
  )
}
