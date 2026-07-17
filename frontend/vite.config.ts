/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  // loadEnv, not process.env: vite reads .env *after* it loads this config, so
  // process.env never sees it. Both knobs below were documented in .env.example and
  // silently did nothing -- a worse trap than no knob at all, because the workaround
  // looks like it should work. A real environment variable still wins.
  const env = { ...loadEnv(mode, process.cwd(), ''), ...process.env }

  // 8080 is what compose publishes by default. This defaulted to 8081 -- the port
  // one developer's machine happened to be free on -- so `pnpm dev` from a fresh
  // clone proxied to nothing.
  const apiTarget = env.VITE_API_PROXY_TARGET ?? 'http://localhost:8080'

  // Overridable because localhost is shared: on a machine running WSL its listeners
  // are mirrored onto Windows' localhost, so a taken port answers with someone
  // else's server rather than failing to bind.
  const port = Number(env.VITE_PORT ?? 5173)

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port,
      // Fail loudly instead of silently hopping to the next port -- a moved dev
      // server is how you end up testing against the wrong thing.
      strictPort: true,
      proxy: {
        // Everything API-side lives under /api, and the prefix is stripped on the way
        // out. Proxying bare /drugs would collide with the SPA's own /drugs/:id
        // route: a click works (React Router never touches the network) but a direct
        // load or a refresh returns JSON instead of the app.
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api/, ''),
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
  }
})
