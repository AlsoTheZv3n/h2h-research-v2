# H2H frontend

React + TypeScript + Tailwind v4 (CSS-first: tokens live in src/index.css, there is
no 	ailwind.config.js). See the [root README](../README.md) for what the project is.

## Scripts

| Command | What |
|---|---|
| `pnpm dev` | Dev server on `VITE_PORT` (5173), proxying `/api` to the backend |
| `pnpm test` | Component tests (Vitest + Testing Library) |
| `pnpm test:e2e` | Playwright, against a **running** stack — start `docker compose up` first |
| `pnpm typecheck` | `tsc -b`, the same check the build runs |
| `pnpm build` | Production build |
| `pnpm lint` | oxlint |

Copy `.env.example` to `.env` to change the port or the proxy target.

## Where the interesting parts are

- `src/components/Fact.tsx` — the four honest states. This component is the product:
  a value, a measured-empty, a failed source and a not-yet-analyzed field must never
  look alike.
- `src/components/PotencyCard.tsx` — an on-target median rather than a row count,
  showing everything it discarded to get there.
- `e2e/` — runs against the real API serving real facts, with no mock layer. Emptying
  the `fact` table makes it fail; that is how you know it is load-bearing.
