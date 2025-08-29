// Auth API client — session/cookie based with CSRF, calling the v1 mirror.
// Endpoints (server-side):
//   GET  /api/v1/auth/csrf/                     -> 204 (sets csrftoken cookie)
//   POST /api/v1/auth/login/                    -> 200 { id, username, email } (sets session)
//   POST /api/v1/auth/logout/                   -> 204 (clears session)
//   GET  /api/v1/auth/me/                       -> 200 { id, username, email } or 401
//   POST /api/v1/auth/password/reset/           -> 204
//   POST /api/v1/auth/password/reset/confirm/   -> 204
//   POST /api/v1/auth/password/change/          -> 204
//   POST /api/v1/auth/register/                 -> 201 or 204 (server may auto-login)

import { http } from './http'

export type User = {
  id: number
  username: string
  email: string
}

export async function getCsrf(): Promise<void> {
  await http<void>('auth/csrf/', { method: 'GET' })
}

export async function login(username: string, password: string): Promise<User> {
  return await http<User>('auth/login/', { method: 'POST', body: { username, password } })
}

export async function logout(): Promise<void> {
  await http<void>('auth/logout/', { method: 'POST' })
}

export async function me(): Promise<User> {
  return await http<User>('auth/me/', { method: 'GET' })
}

// ---------------- Password Reset (unauthenticated) ----------------

export async function requestPasswordReset(email: string): Promise<void> {
  await http<void>('auth/password/reset/', { method: 'POST', body: { email } })
}

export async function resetPasswordConfirm(args: {
  uid: string
  token: string
  newPassword1: string
  newPassword2: string
}): Promise<void> {
  const { uid, token, newPassword1, newPassword2 } = args
  await http<void>('auth/password/reset/confirm/', {
    method: 'POST',
    body: {
      uid,
      token,
      new_password1: newPassword1,
      new_password2: newPassword2,
    },
  })
}

// ---------------- Password Change (authenticated) -----------------

/**
 * Change the current user's password. Requires a logged-in session & CSRF.
 * Server returns 204 on success; throws DRF-shaped errors otherwise.
 */
export async function passwordChange(
  oldPassword: string,
  newPassword1: string,
  newPassword2: string
): Promise<void> {
  await http<void>('auth/password/change/', {
    method: 'POST',
    body: {
      old_password: oldPassword,
      new_password1: newPassword1,
      new_password2: newPassword2,
    },
  })
}

// ---------------- Registration (if enabled) -----------------------

/**
 * Register a new account. If registration is disabled, the server may respond
 * with 403/404; the caller should surface a friendly message. Some backends
 * auto-login on success; your Register page already handles both flows by
 * calling refresh() and navigating home.
 */
export async function register(
  username: string,
  email: string,
  password1: string,
  password2: string
): Promise<void> {
  await http<void>('auth/register/', {
    method: 'POST',
    body: {
      username,
      email,
      password1,
      password2,
    },
  })
}
