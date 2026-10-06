import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API runs separately (python -m jobdesk serve). In dev, Vite proxies to it, and edits to
// the dashboard's code show up in the open tab straight away.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    host: '127.0.0.1',
    proxy: {
      '/api': { target: 'http://127.0.0.1:8780', changeOrigin: false },
      '/files': { target: 'http://127.0.0.1:8780' },
    },
  },
})
