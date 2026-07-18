import { Link, Outlet, useLocation } from 'react-router-dom'

/**
 * The app shell: brand plus a two-tab nav, Drugs and Cancers.
 *
 * A single catalog needed no navigation, so the header was branding only. With two
 * entities, switching catalogs is a primary action -- and a per-page "back to the
 * catalog" link is not navigation. The active tab is computed from the path, not from
 * NavLink's exact match, so a drug or cancer *detail* page keeps its catalog's tab lit:
 * `/drugs/:id` belongs to Drugs, `/cancers/:id` to Cancers.
 */
export function App() {
  const { pathname } = useLocation()
  // The drug overview lives at "/", detail at "/drugs/:id" -- both are the Drugs tab.
  const onCancers = pathname.startsWith('/cancers')
  const onDrugs = !onCancers

  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-line bg-card">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-3">
          <Link to="/" className="text-sm font-semibold tracking-tight text-ink">
            H2H
          </Link>
          <span className="hidden text-xs text-ink-faint sm:inline">
            Sourced evidence for oncology drugs and cancers
          </span>
          <nav className="ml-auto flex items-center gap-1" aria-label="Primary">
            <Tab to="/" label="Drugs" active={onDrugs} />
            <Tab to="/cancers" label="Cancers" active={onCancers} />
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-6">
        <Outlet />
      </main>
    </div>
  )
}

function Tab({ to, label, active }: { to: string; label: string; active: boolean }) {
  return (
    <Link
      to={to}
      aria-current={active ? 'page' : undefined}
      data-testid={`nav-${label.toLowerCase()}`}
      className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
        active
          ? 'bg-accent-bg font-medium text-accent'
          : 'text-ink-muted hover:text-accent'
      }`}
    >
      {label}
    </Link>
  )
}
