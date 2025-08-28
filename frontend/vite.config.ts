import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Same-origin dev proxy to Django (so cookies/CSRF behave normally)
      '/api': 'http://127.0.0.1:8000',
      '/p': 'http://127.0.0.1:8000',
      '/admin': 'http://127.0.0.1:8000'
    }
  },
  test: {
    environment: 'jsdom',
    setupFiles: 'src/test/setup.ts',
    globals: true
  }
})
