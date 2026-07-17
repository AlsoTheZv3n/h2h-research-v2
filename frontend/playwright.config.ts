import { defineConfig, devices } from '@playwright/test'

const PORT = Number(process.env.VITE_PORT ?? 5174)
const BASE_URL = process.env.E2E_BASE_URL ?? `http://localhost:${PORT}`

/**
 * E2E runs against the REAL backend serving REAL enriched facts. There is no mock
 * layer, deliberately.
 *
 * The most expensive defect in this project was a backend where no production path
 * ever called an adapter: every test was green because each laid down its own data,
 * so the API would have served `facts: {}` in production. A frontend suite mocking
 * the facts endpoint would rebuild exactly that blind spot one layer up -- looking
 * "done" while nothing real flows through. So these tests fail if the backend is not
 * actually serving facts, and that failure is the point.
 */
export default defineConfig({
  testDir: './e2e',
  // Seeds the deterministic source_failed fixture into the real database.
  globalSetup: './e2e/global-setup.ts',
  // The recording script is not a test.
  testIgnore: ['**/demo.record.ts', '**/global-setup.ts'],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'pnpm dev',
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 60_000,
  },
})
