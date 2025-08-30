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
import { Link as RouterLink } from 'react-router-dom'
import * as api from '../api/auth'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Prime CSRF cookie; ignore if already present.
  useEffect(() => {
    void api.getCsrf().catch(() => {})
  }, [])

  const onSubmit = useCallback(async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      await api.requestPasswordReset(email.trim())
      // Non-enumerating response: always show "sent"
      setSent(true)
    } catch (err: any) {
      if (err?.status === 429) setError('Too many attempts; please wait a moment.')
      else setError('Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }, [email])

  return (
    <Container maxWidth="xs">
      <Box component="main" sx={{ mt: 8 }}>
        <Typography variant="h5" fontWeight={700} gutterBottom>
          Forgot your password?
        </Typography>

        {sent ? (
          <Stack spacing={2}>
            <Typography>
              If that email exists in our system, we’ve sent password reset instructions.
            </Typography>
            <Button component={RouterLink} to="/login" variant="text" size="small" sx={{ textTransform: 'none' }}>
              Return to sign in
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
                  id="email"
                  label="Email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                  required
                  fullWidth
                  autoFocus
                />
                <Button type="submit" variant="contained" disabled={loading}>
                  {loading ? 'Sending…' : 'Send reset link'}
                </Button>
              </Stack>
            </Box>
          </>
        )}
      </Box>
    </Container>
  )
}
