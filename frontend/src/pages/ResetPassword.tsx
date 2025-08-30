import React, { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
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
import { Link as RouterLink, useLocation } from 'react-router-dom'

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

  // Prime CSRF cookie; ignore if already present.
  useEffect(() => {
    void api.getCsrf().catch(() => {})
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
    <Container maxWidth="xs">
      <Box component="main" sx={{ mt: 8 }}>
        <Typography variant="h5" fontWeight={700} gutterBottom>
          Reset your password
        </Typography>

        {ok ? (
          <Stack spacing={2}>
            <Typography>Your password has been reset.</Typography>
            <Button component={RouterLink} to="/login" variant="text" size="small" sx={{ textTransform: 'none' }}>
              Go to sign in
            </Button>
          </Stack>
        ) : (
          <>
            {error && (
              <Alert severity="error" sx={{ mb: 2 }} role="alert">
                {error}
              </Alert>
            )}
            <Box component="form" onSubmit={onSubmit} noValidate>
              <Stack spacing={2}>
                <TextField
                  id="p1"
                  label="New password"
                  type="password"
                  autoComplete="new-password"
                  value={p1}
                  onChange={(e) => setP1(e.target.value)}
                  disabled={loading}
                  required
                  fullWidth
                  autoFocus
                />
                <TextField
                  id="p2"
                  label="Confirm new password"
                  type="password"
                  autoComplete="new-password"
                  value={p2}
                  onChange={(e) => setP2(e.target.value)}
                  disabled={loading}
                  required
                  fullWidth
                />
                <Button type="submit" variant="contained" disabled={loading}>
                  {loading ? 'Resetting…' : 'Reset password'}
                </Button>
                <Typography>
                  Don’t have a link?{' '}
                  <Button component={RouterLink} to="/forgot-password" variant="text" size="small" sx={{ textTransform: 'none' }}>
                    Request a new one
                  </Button>
                </Typography>
              </Stack>
            </Box>
          </>
        )}
      </Box>
    </Container>
  )
}
