import type { SynthesisStatement } from '../../api/types'

/**
 * The page-level "so what" (C1): a short set of derived statements that lead the page and orient
 * the reader before the evidence blocks. Each is a disclosed threshold rule computed server-side
 * (never generated prose), and each LINKS to the block it came from so the reader can check it.
 *
 * Renders nothing when the synthesis is empty -- an unenriched or thin cancer earns no "so what",
 * rather than a panel of confident nothings. The statements themselves are only ever present when
 * their inputs were (the backend withholds, never substitutes a zero), so this component trusts
 * what it is given and simply lays it out.
 */
export function SynthesisPanel({ synthesis }: { synthesis?: SynthesisStatement[] }) {
  if (!synthesis || synthesis.length === 0) return null
  return (
    <section
      data-testid="synthesis"
      aria-label="What the evidence adds up to"
      className="mb-4 rounded-lg border border-line bg-card p-3"
    >
      <h2 className="mb-1.5 text-xs text-ink-faint">What the evidence adds up to</h2>
      <ul className="space-y-1">
        {synthesis.map((s) => (
          <li key={`${s.block}-${s.text}`} className="text-sm text-ink">
            {/* Links to its own block -- the reading is a claim the reader can jump to and check. */}
            <a href={`#${s.block}`} className="hover:underline" data-testid="synthesis-statement">
              {s.text}
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}
