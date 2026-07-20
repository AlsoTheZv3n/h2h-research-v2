import type { SelectivityProfile, SelectivityTarget, SourcedFact } from '../api/types'
import { CitationChip } from './CitationChip'
import { FactGate } from './FactGate'
import { Card, NotApplicable } from './Card'
import { formatNm } from '../format'

/**
 * Selectivity profile — what the drug hits, and how selectively.
 *
 * Replaces the old "on-target median + excluded dump". The rows the old card discarded as
 * "excluded" ARE the profile: rank every measured single-protein target by potency, take the
 * most potent as the REFERENCE (the field declares no primary target), and place every other
 * target as a fold-difference from it. A target within the disclosed threshold (100×) of the
 * reference is a real target; beyond it, incidental. The reader's question -- "what does this
 * mainly target, and how selectively?" -- is answered by the ranking and the fold window, not
 * by one number.
 *
 * Disciplines carried from the domain layer, disclosed on the card, never generated prose:
 *   - potency spans orders of magnitude, so the axis is LOG (fold), never linear nM;
 *   - the selective/multi-target verdict is a COUNT against the 100× rule, stated inline;
 *   - the single-measurement targets and the cell-based/censored/non-nM rows are set aside but
 *     COUNTED, shown as a disclosed footnote (A4 turns a dominant exclusion into a warning).
 */
export function PotencyCard({ facts, isBiologic }: { facts?: SourcedFact[]; isBiologic: boolean }) {
  if (isBiologic) {
    return (
      <Card title="Selectivity & potency">
        <NotApplicable reason="Not applicable — this drug is not a small molecule, so it has no small-molecule binding curve; that data model is out of scope for v1." />
      </Card>
    )
  }

  return (
    <Card
      title="Selectivity & potency"
      note="Targets ranked by potency · fold vs the most potent (log scale)"
    >
      <FactGate facts={facts}>{(fact) => <SelectivityBody fact={fact} />}</FactGate>
    </Card>
  )
}

/** No decimals once the fold is in the tens; one below, where 2.6× reads differently from 3×. */
const formatFold = (f: number) => (f >= 10 ? String(Math.round(f)) : f.toFixed(1))

/** Compact decade labels for the axis (1×, 10× … 1k×, 10k×), so 5-6 ticks never collide in the
 *  narrow track the way "10000×" would. */
const formatFoldTick = (f: number) => (f >= 1000 ? `${f / 1000}k×` : `${f}×`)

/** The decades 1, 10, 100 … up to the axis max -- the log ticks. */
function decades(max: number): number[] {
  const out: number[] = []
  for (let d = 1; d <= max; d *= 10) out.push(d)
  return out
}

function SelectivityBody({ fact }: { fact: SourcedFact }) {
  const profile = fact.value as SelectivityProfile | null
  const ref = profile?.reference ?? null

  // Honest empty: nothing corroborated to rank. Say WHY from the counts (single-measurement
  // targets, or everything set aside), never a bare "no data" -- the set-aside rows are the reason.
  if (!profile || !ref) return <NoProfile profile={profile ?? null} fact={fact} />

  const { targets, n_targets, threshold_fold, n_protein_rows } = profile

  // Show every real target (within threshold); give a few beyond-threshold ones for context, and
  // disclose the rest as a count -- truncating incidental targets is honest, hiding real ones is not.
  // targets is ranked most-potent-first, so `beyond` keeps that order: the two shown are the two
  // NEAREST beyond the threshold (the drop-off past the last real target), the rest disclosed as a
  // count. Two, not more, so a lone far-out outlier (imatinib's 14,000× cruzipain) can't stretch
  // the log axis and compress the real targets into a sliver.
  const real = targets.filter((t) => t.is_target)
  const beyond = targets.filter((t) => !t.is_target)
  const shown = [...real, ...beyond.slice(0, 2)]
  const beyondHidden = beyond.length - beyond.slice(0, 2).length

  // Log axis in FOLD (1× = reference, at the left). A decade floor of 1000× keeps the 100×
  // threshold gridline legible even for a single-target drug; otherwise the next decade above the
  // weakest SHOWN target (a hidden ultra-weak target must not stretch the axis).
  const maxFold = Math.max(...shown.map((t) => t.fold_vs_reference), 1)
  const axisMax = Math.max(1000, Math.pow(10, Math.ceil(Math.log10(maxFold))))
  const logMax = Math.log10(axisMax)
  const pos = (fold: number) => (Math.log10(Math.max(fold, 1)) / logMax) * 100
  const thresholdPct = pos(threshold_fold)
  const grid = 'grid grid-cols-[minmax(6rem,9rem)_4.5rem_1fr_3rem] items-center gap-x-2'

  return (
    <>
      {/* Derived verdict, rule disclosed in the line itself (no generated prose): the count of
          targets within the threshold of the most potent. 1 = selective; more = multi-target. */}
      <p className="text-sm">
        <span className="font-semibold text-ink" data-testid="selectivity-verdict">
          {n_targets <= 1 ? 'Selective' : 'Multi-target'}
        </span>
        <span className="text-ink-muted">
          {' — most potent on '}
          <span className="font-medium text-ink">{ref.target_pref_name}</span> ({formatNm(ref.median_nm)}{' '}
          nM);{' '}
          {n_targets <= 1 ? 'no other target within 100× of it' : `${n_targets} targets within 100× of it`}
        </span>
        <CitationChip fact={fact} />
      </p>

      {/* Ranked, log-scaled. Each row: target, median nM (linear label), a log-fold bar with the
          100× threshold marked, the fold. Targets beyond the threshold are faded -- incidental. */}
      <ul className="mt-3 space-y-1.5" data-testid="selectivity-profile">
        {shown.map((t) => (
          <TargetRow key={t.target_chembl_id} t={t} pos={pos} thresholdPct={thresholdPct} grid={grid} />
        ))}
        {/* Log axis: decades, 100× (the threshold) marked. Makes the scale explicit. */}
        <li className={`${grid} pt-0.5 text-[10px] text-ink-faint`} aria-hidden>
          <span />
          <span />
          <span className="relative h-3">
            {decades(axisMax).map((d) => (
              <span
                key={d}
                className={`absolute -translate-x-1/2 ${d === threshold_fold ? 'font-medium text-ink-muted' : ''}`}
                style={{ left: `${pos(d)}%` }}
              >
                {formatFoldTick(d)}
              </span>
            ))}
          </span>
          <span />
        </li>
      </ul>

      <ProfileFootnote profile={profile} nProteinRows={n_protein_rows} beyondHidden={beyondHidden} />
    </>
  )
}

function TargetRow({
  t,
  pos,
  thresholdPct,
  grid,
}: {
  t: SelectivityTarget
  pos: (fold: number) => number
  thresholdPct: number
  grid: string
}) {
  const end = pos(t.fold_vs_reference)
  const isRef = t.fold_vs_reference <= 1
  return (
    <li data-testid="selectivity-row" className={`${grid} text-xs`}>
      <span className="truncate text-ink" title={t.target_pref_name}>
        {t.target_pref_name}
      </span>
      <span className="text-right tabular-nums text-ink-muted">{formatNm(t.median_nm)} nM</span>
      <span className="relative h-3" title={`n=${t.n} measurement${t.n === 1 ? '' : 's'}`}>
        {/* the 100× threshold — same position every row, so the repeats form one continuous rule */}
        <span
          className="absolute top-0 bottom-0 border-l border-dashed border-line"
          style={{ left: `${thresholdPct}%` }}
          aria-hidden
        />
        {/* the log-fold bar, from the reference (left) to this target's fold */}
        <span
          data-testid={t.is_target ? 'bar-target' : 'bar-incidental'}
          className={`absolute top-1/2 h-1.5 -translate-y-1/2 rounded-sm ${t.is_target ? 'bg-accent' : 'bg-line'}`}
          style={{ left: 0, width: `${Math.max(end, 1.5)}%` }}
        />
      </span>
      <span
        className={`text-right tabular-nums ${t.is_target ? 'text-ink-muted' : 'text-ink-faint'}`}
      >
        {isRef ? 'ref' : `${formatFold(t.fold_vs_reference)}×`}
      </span>
    </li>
  )
}

/** The disclosed set-aside line: what did not rank, and the rule the ranking followed. A2 shows
 *  the counts plainly; A4 escalates a dominant exclusion into a warning. */
function ProfileFootnote({
  profile,
  nProteinRows,
  beyondHidden,
}: {
  profile: SelectivityProfile
  nProteinRows: number
  beyondHidden: number
}) {
  const parts: string[] = []
  if (beyondHidden > 0) parts.push(`${beyondHidden} more beyond 100× (incidental)`)
  if (profile.n_uncorroborated_targets > 0)
    parts.push(`${profile.n_uncorroborated_targets} measured once (not ranked)`)
  if (profile.n_excluded_rows > 0)
    parts.push(`${profile.n_excluded_rows} rows set aside (cell-based, censored, non-nM)`)

  return (
    <p
      className="mt-2 border-t border-line pt-1.5 text-[11px] text-ink-faint"
      data-testid="selectivity-setaside"
    >
      Ranking over {nProteinRows} exact single-protein measurement{nProteinRows === 1 ? '' : 's'};
      most potent = reference, within 100× = a target.
      {parts.length > 0 && <> Set aside: {parts.join(' · ')}.</>}
    </p>
  )
}

/** Nothing corroborated to rank. The reason is in the counts, and it is disclosed. */
function NoProfile({ profile, fact }: { profile: SelectivityProfile | null; fact: SourcedFact }) {
  const reason = !profile
    ? 'No potency measurements on record.'
    : profile.n_uncorroborated_targets > 0 && profile.n_protein_rows === 0
      ? `${profile.n_uncorroborated_targets} target${profile.n_uncorroborated_targets === 1 ? '' : 's'} measured only once — too few to rank a selectivity claim.`
      : profile.n_excluded_rows > 0
        ? `No single-protein binding measurements to rank; ${profile.n_excluded_rows} row${profile.n_excluded_rows === 1 ? '' : 's'} set aside (cell-based, censored, or non-nM).`
        : 'No single-protein potency to rank.'
  return (
    <p className="text-sm text-ink-muted" data-testid="selectivity-empty">
      {reason}
      <CitationChip fact={fact} />
    </p>
  )
}
