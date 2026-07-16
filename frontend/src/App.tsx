import { Link, Outlet } from 'react-router-dom'

export function App() {
  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-line bg-card">
        <div className="mx-auto flex max-w-6xl items-baseline gap-3 px-6 py-3">
          <Link to="/" className="text-sm font-semibold tracking-tight text-ink">
            H2H
          </Link>
          <span className="text-xs text-ink-faint">
            Sourced evidence for oncology drug programs
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-6">
        <Outlet />
      </main>
    </div>
  )
}
