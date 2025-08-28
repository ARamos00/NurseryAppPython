import { http } from './http'

export type User = { id: number; username: string; email: string }

export async function getCsrf(): Promise<void> {
  await http<void>('auth/csrf/', { method: 'GET', unsafe: false })
}

export async function login(username: string, password: string): Promise<User> {
  return await http<User>('auth/login/', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
    headers: { 'Content-Type': 'application/json' }
  })
}

export async function logout(): Promise<void> {
  await http<void>('auth/logout/', { method: 'POST' })
}

export async function me(): Promise<User> {
  return await http<User>('auth/me/', { method: 'GET', unsafe: false })
}

export async function register(username: string, email: string, password1: string, password2: string): Promise<User> {
  return await http<User>('auth/register/', {
    method: 'POST',
    body: JSON.stringify({ username, email, password1, password2 }),
    headers: { 'Content-Type': 'application/json' }
  })
}

export async function passwordChange(old_password: string, new_password1: string, new_password2: string): Promise<void> {
  await http<void>('auth/password/change/', {
    method: 'POST',
    body: JSON.stringify({ old_password, new_password1, new_password2 }),
    headers: { 'Content-Type': 'application/json' }
  })
}
