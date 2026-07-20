import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { DrugStatus, SourcedFact, TargetLandscape, TargetLandscapeEntry } from '../api/types'
import { Card } from './Card'
import { CitationChip } from './CitationChip'
import { FactGate } from './FactGate'
import { associationStrength, evidenceContributions, STRONG_ASSOCIATION } from '../association'

/**
 * The cancer's target landscape: the top associated targets from Open Targets, each with
 * its association score, tractability, drugged/unexploited status and the evidence behind
 * it. Handles the honest states itself (mirroring PotencyCard): pending while enriching, a
 * calm amber chip on an outage, a muted "none" for a real empty -- never an outage rendered
 * as "no targets".
 *
 * The drugged status is the cell this card exists for: a high-association target with no
 * drug ANYWHERE is the finding. It comes from Open Targets (the world), not our catalog,
 * and is indication-agnostic and target-level -- "a drug exists against this target", never
 * "approved for this cancer". `unknown` (not measured) and `unexploited` (measured, none)
 * are kept visibly distinct: collapsing them would resurrect the None-vs-0 lie one level up.
 */
export function TargetLandscapeCard({
  id,
  facts,
  catalogDrugByTarget,
}: {
  id?: string
  facts?: SourcedFact[]
  /** Ensembl id -> a catalog drug's ChEMBL id, for the per-target "open a brief" link. */
  catalogDrugByTarget?: Record<string, string>
}) {
  return (
    <Card
      id={id}
      title="Target landscape"
      note={`Top associated targets · Open Targets association strength (strong = score ≥ ${STRONG_ASSOCIATION})`}
    >
      <FactGate facts={facts}>
        {(fact) => {
          // Tolerate both fact shapes. The current value is {threshold, n_strong, targets}; a
          // fact stored before that reshape is a bare target array. Reading either keeps an
          // already-enriched cancer's card rendering its targets until stale-while-revalidate
          // upgrades it -- an old fact just lacks the strong count, which lives on the stat card.
          const value = fact.value as TargetLandscape | TargetLandscapeEntry[] | null
          const targets = Array.isArray(value) ? value : (value?.targets ?? [])
          if (fact.status === 'empty' || targets.length === 0) {
            return (
              <p className="text-sm text-ink-faint">
                No associated targets
                <CitationChip fact={fact} />
              </p>
            )
          }
          return (
            <TargetLandscapeBody
              targets={targets}
              fact={fact}
              catalogDrugByTarget={catalogDrugByTarget}
            />
          )
        }}
      </FactGate>
    </Card>
  )
}

// The four drugged states, each with a distinct look (fill vs contrast vs faint) AND a label
// that WRITES OUT the claim, so no term of art (the harness read "unexploited" as "not in this
// catalog" -- the opposite of what it means). The label says WHAT (a drug / no drug) and, for
// the finding, its SCOPE (anywhere = the world, not our catalog). "no drug anywhere" takes the
// high-contrast inverted chip to pull the eye; "not measured" stays faint (a gap is not a
// finding). The data states (approved/clinical/unexploited/unknown) are unchanged -- only the
// wording. Catalog availability is a SEPARATE, weaker signal (the "in catalog" link), never
// this badge, so catalog absence can never read as "no drug anywhere".
const STATUS_STYLE: Record<DrugStatus, { label: string; className: string; title: string }> = {
  approved: {
    label: 'approved drug',
    className: 'bg-accent-bg text-accent',
    title:
      'An approved drug exists against this target, somewhere in the world (Open Targets). ' +
      'Indication-agnostic — it may be approved for a different cancer, not necessarily this one.',
  },
  clinical: {
    label: 'in trials',
    className: 'bg-partial-bg text-partial',
    title:
      'In clinical trials against this target somewhere — candidates exist, none approved yet.',
  },
  unexploited: {
    label: 'no drug anywhere',
    className: 'bg-ink text-card',
    title:
      'No drug exists against this target anywhere in the world (Open Targets) — a strong ' +
      'association with no therapeutic. NOT the same as "we do not hold one in this catalog".',
  },
  unknown: {
    label: 'not measured',
    className: 'text-ink-faint ring-1 ring-line',
    title: 'Drug status unavailable from Open Targets — not measured, which is not "no drug".',
  },
}

const FILTERS: { value: string; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'unexploited', label: 'No drug anywhere' },
  { value: 'approved', label: 'Approved drug' },
  { value: 'clinical', label: 'In trials' },
  { value: 'unknown', label: 'Not measured' },
]

// Pre-flag facts (before drug_status shipped) have no status -> "unknown", never a guess.
const statusOf = (t: TargetLandscapeEntry): DrugStatus => t.drug_status ?? 'unknown'

function TargetLandscapeBody({
  targets,
  fact,
  catalogDrugByTarget,
}: {
  targets: TargetLandscapeEntry[]
  fact: SourcedFact
  catalogDrugByTarget?: Record<string, string>
}) {
  const [status, setStatus] = useState('')
  const filtered = useMemo(
    () => (status ? targets.filter((t) => statusOf(t) === status) : targets),
    [targets, status],
  )

  return (
    <>
      <div className="mb-2 flex items-center justify-between gap-2">
        <select
          aria-label="Filter targets by drug status"
          data-testid="landscape-filter-status"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-line bg-card px-2 py-1 text-xs text-ink focus:outline-none"
        >
          {FILTERS.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
        <span className="text-[11px] text-ink-faint">
          Drug status: is there a drug against this target anywhere? (Open Targets, any indication)
        </span>
      </div>

      <ul className="divide-y divide-line" data-testid="target-landscape">
        {filtered.map((t) => {
          // The catalog-link: a drug WE hold that acts on this target, keyed by Ensembl id.
          // Absent -> plain symbol ("drugged, no link"), never a dead link and never a claim
          // about the target's drugged status, which is the badge's job, not this link's.
          const catalogDrug = t.ensembl_id ? catalogDrugByTarget?.[t.ensembl_id] : undefined
          return (
          <li key={t.symbol} data-testid="landscape-row" className="flex items-center gap-2 py-1.5 text-sm">
            <span className="w-16 shrink-0 font-medium">
              {/* The symbol drills into the target's own page -- the cancers it drives and the
                  drugs against it. Every displayed row carries an Ensembl id; a defensive plain
                  span covers the (unreached) case where one is missing. */}
              {t.ensembl_id ? (
                <Link
                  to={`/targets/${t.ensembl_id}`}
                  data-testid="landscape-target-link"
                  title="Open this target's page"
                  className="text-accent hover:underline"
                >
                  {t.symbol}
                </Link>
              ) : (
                <span className="text-ink">{t.symbol}</span>
              )}
            </span>
            {/* B5: lead with the qualitative strength (strong vs moderate, against the 0.5 cut);
                the 0-1 score travels as faint detail, never a bare threshold to decode. */}
            <span className="w-20 shrink-0 text-xs" title="Open Targets association strength">
              <span className={associationStrength(t.score) === 'strong' ? 'text-ink' : 'text-ink-muted'}>
                {associationStrength(t.score)}
              </span>{' '}
              <span className="text-[10px] tabular-nums text-ink-faint">{t.score.toFixed(2)}</span>
            </span>
            <span className="flex shrink-0 items-center gap-1">
              <Tractable on={t.sm_tractable} label="SM" title="Small-molecule tractable" />
              <Tractable on={t.ab_tractable} label="AB" title="Antibody tractable" />
              <DrugStatusBadge status={statusOf(t)} />
            </span>
            <span className="ml-auto flex min-w-0 items-center gap-3">
              <span
                className="min-w-0 truncate text-[11px] text-ink-faint"
                title={`contributing evidence: ${evidenceContributions(t.evidence_types).join(', ')}`}
              >
                {/* B5: the evidence TYPES that contributed to the score, in reader words -- what the
                    score is built from (the interpretable thing), not the weighting formula. */}
                {evidenceContributions(t.evidence_types).slice(0, 2).join(' · ')}
                {/* mark the truncation, so two shown never read as all the evidence channels */}
                {t.evidence_types.length > 2 && ` +${t.evidence_types.length - 2}`}
              </span>
              {/* A weaker, separate signal from the badge: we hold a drug in our catalog against
                  this target. A WORDED link, set apart from the status badge, so it reads as an
                  action (open a brief), not a status -- the harness read the old bare ℞ glyph, sat
                  beside the badges, as a drugged-status marker. Absent -> nothing. */}
              {catalogDrug && (
                <Link
                  to={`/drugs/${catalogDrug}`}
                  data-testid="landscape-catalog-link"
                  title="A drug in our catalog acts on this target — open its brief"
                  className="shrink-0 whitespace-nowrap text-[11px] text-accent hover:underline"
                >
                  in catalog ↗
                </Link>
              )}
            </span>
          </li>
          )
        })}
        {filtered.length === 0 && (
          <li className="py-3 text-center text-sm text-ink-faint">No targets with this status.</li>
        )}
      </ul>
      <div className="mt-2 text-right">
        <CitationChip fact={fact} />
      </div>
    </>
  )
}

/** A modality badge: lit when the target is tractable that way, struck through when not. */
function Tractable({ on, label, title }: { on: boolean; label: string; title: string }) {
  return (
    <span
      title={title}
      className={`rounded px-1 text-[10px] font-medium ${
        on ? 'bg-accent-bg text-accent' : 'text-ink-faint line-through'
      }`}
    >
      {label}
    </span>
  )
}

/** The drugged/unexploited/unknown marker — the card's reason to exist. */
function DrugStatusBadge({ status }: { status: DrugStatus }) {
  // Fall back to the unknown style if a status outside the union ever reaches here (malformed
  // persisted data): degrade to "unknown", never throw and blank the page (there is no error
  // boundary). Unreachable through the current backend, which emits only the four.
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.unknown
  return (
    <span
      data-testid={`drug-status-${status}`}
      title={s.title}
      className={`rounded px-1 text-[10px] font-medium ${s.className}`}
    >
      {s.label}
    </span>
  )
}
