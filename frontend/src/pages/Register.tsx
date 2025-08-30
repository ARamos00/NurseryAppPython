import React, { FormEvent, useCallback, useEffect, useState } from 'react'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
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

export default function RegisterPage() {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password1, setPassword1] = useState('')
  const [password2, setPassword2] = useState('')
  const [nonFieldError, setNonFieldError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const nav = useNavigate()
  const { refresh } = useAuth()

  // Prime CSRF cookie (safe to ignore errors if already present)
  useEffect(() => {
    void (async () => {
      try {
        await api.getCsrf()
      } catch {
        /* ignore */
      }
    })()
  }, [])

  const onSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      setLoading(true)
      setNonFieldError(null)
      try {
        await api.register(username.trim(), email.trim(), password1, password2)
        await refresh()
        nav('/', { replace: true })
      } catch (err: any) {
        if (err?.status === 400) {
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
    },
    [username, email, password1, password2, refresh, nav],
  )

  return (
    <Container maxWidth="xs">
      <Box component="main" sx={{ mt: 8 }}>
        <Typography variant="h5" fontWeight={700} gutterBottom>
          Create your account
        </Typography>

        {nonFieldError && (
          <Alert severity="error" sx={{ mb: 2 }} role="alert">
            {nonFieldError}
          </Alert>
        )}

        <Box component="form" onSubmit={onSubmit} noValidate>
          <Stack spacing={2}>
            <TextField
              id="username"
              label="Username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              required
              fullWidth
              autoFocus
            />
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
            />
            <TextField
              id="password1"
              label="Password"
              type="password"
              autoComplete="new-password"
              value={password1}
              onChange={(e) => setPassword1(e.target.value)}
              disabled={loading}
              required
              fullWidth
            />
            <TextField
              id="password2"
              label="Confirm password"
              type="password"
              autoComplete="new-password"
              value={password2}
              onChange={(e) => setPassword2(e.target.value)}
              disabled={loading}
              required
              fullWidth
            />
            <Button type="submit" variant="contained" disabled={loading}>
              {loading ? 'Creating account…' : 'Create account'}
            </Button>
          </Stack>
        </Box>

        <Typography sx={{ mt: 2 }}>
          Already have an account?{' '}
          <Button
            component={RouterLink}
            to="/login"
            variant="text"
            size="small"
            sx={{ textTransform: 'none' }}
          >
            Sign in
          </Button>
        </Typography>
      </Box>
    </Container>
  )
}
