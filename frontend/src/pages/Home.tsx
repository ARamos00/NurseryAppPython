import React from 'react'
import { useAuth } from '../auth/AuthContext'

export default function Home() {
  const { user, logout } = useAuth()
  return (
    <main style={{ maxWidth: 720, margin: '2rem auto', padding: '1rem' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>Nursery Tracker</h1>
        <div>
          <span style={{ marginRight: 12 }}>Signed in as <strong>{user?.username}</strong></span>
          <button onClick={() => logout()}>Log out</button>
        </div>
      </header>
      <section style={{ marginTop: 24 }}>
        <p>Protected area. Add app routes here.</p>
      </section>
    </main>
  )
}
