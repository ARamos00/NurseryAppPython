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
