/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Default API base is empty, so the browser calls same-origin /drugs and the proxy
// below forwards it: no CORS in dev, and a deployment can point VITE_API_BASE_URL
// at a real host without touching code.
const API_TARGET = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8081'

// Overridable because localhost is shared: on a machine running WSL, its listeners
// are mirrored onto Windows' localhost, so a taken port answers with someone else's
// server rather than failing to bind. 5173 is exactly that here.
const PORT = Number(process.env.VITE_PORT ?? 5173)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: PORT,
    // Fail loudly instead of silently hopping to the next port -- a moved dev server
    // is how you end up testing against the wrong thing.
    strictPort: true,
    proxy: {
      // Everything API-side lives under /api, and the prefix is stripped on the way
      // out. Proxying bare /drugs would collide with the SPA's own /drugs/:id route:
      // a click works (React Router never touches the network) but a direct load or
      // a refresh returns JSON instead of the app. The prefix keeps the two
      // namespaces from ever meeting.
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // E2E lives in Playwright and hits the real API; Vitest must not pick it up.
    exclude: ['**/node_modules/**', '**/e2e/**'],
  },
})
