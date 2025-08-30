import React, { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { Link as RouterLink, useLocation, useNavigate } from 'react-router-dom'
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

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const nav = useNavigate()
  const loc = useLocation()
  const { refresh } = useAuth()

  const next = useMemo(
    () => new URLSearchParams(loc.search).get('next') || '/',
    [loc.search],
  )

  // Prime CSRF cookie (non-fatal if already present).
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
      setError(null)
      try {
        await api.login(username.trim(), password)
        await refresh()
        nav(next, { replace: true })
      } catch (err: any) {
        if (err?.status === 400 || err?.status === 401)
          setError('Invalid username or password.')
        else if (err?.status === 429)
          setError('Too many attempts; please wait.')
        else setError('Something went wrong. Please try again.')
      } finally {
        setLoading(false)
      }
    },
    [username, password, refresh, nav, next],
  )

  return (
    <Container maxWidth="xs">
      <Box component="main" sx={{ mt: 8 }}>
        <Typography variant="h5" fontWeight={700} gutterBottom>
          Sign in
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }} role="alert">
            {error}
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
              id="password"
              label="Password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              required
              fullWidth
            />
            <Button type="submit" variant="contained" disabled={loading}>
              {loading ? 'Signing in…' : 'Sign in'}
            </Button>
          </Stack>
        </Box>

        <Typography sx={{ mt: 2 }}>
          New here?{' '}
          <Button
            component={RouterLink}
            to="/register"
            variant="text"
            size="small"
            sx={{ textTransform: 'none' }}
          >
            Create an account
          </Button>
        </Typography>
      </Box>
    </Container>
  )
}
