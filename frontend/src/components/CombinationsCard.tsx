import type { Combinations, CombinationExample, SourcedFact } from '../api/types'
import { formatCount } from '../format'
import { Card } from './Card'
import { CitationChip } from './CitationChip'
import { FactGate } from './FactGate'

/**
 * A drug's OBSERVED combinations vs comparisons, from ClinicalTrials.gov arm structure.
 *
 * The load-bearing distinction: a trial naming drug A and drug B may be A+B (a combination) or
 * A vs B (a comparison) -- opposite meanings that ONLY the arm structure separates, never name
 * co-occurrence. Multi-drug trials with no arm-level assignment are dropped, never guessed, and
 * the dropped count is footnoted for honesty. Honest states via FactGate: an outage is the amber
 * chip, never "no combinations"; a real EMPTY is "none observed". Counts travel with the scanned
 * sample, and the drug-name match is owned in words.
 */
export function CombinationsCard({ id, facts }: { id?: string; facts?: SourcedFact[] }) {
  return (
    <Card
      id={id}
      title="Observed combinations"
      note="From ClinicalTrials.gov arm structure — a single arm with ≥2 drugs is a combination; separate single-drug arms are a comparison"
    >
      <FactGate facts={facts}>
        {(fact) => {
          const data = fact.value as Combinations | null
          if (fact.status === 'empty' || !data) {
            return (
              <p className="text-sm text-ink-faint">
                No combination or comparison could be classified from this drug's registered trials
                <CitationChip fact={fact} />
              </p>
            )
          }
          return <CombinationsBody data={data} fact={fact} />
        }}
      </FactGate>
    </Card>
  )
}

function CombinationsBody({ data, fact }: { data: Combinations; fact: SourcedFact }) {
  return (
    <>
      <p className="text-xs text-ink-muted" data-testid="combinations-summary">
        <span className="font-medium text-ink">{formatCount(data.n_combination)}</span> combination
        {data.n_combination === 1 ? '' : 's'} and{' '}
        <span className="font-medium text-ink">{formatCount(data.n_comparison)}</span> comparison
        {data.n_comparison === 1 ? '' : 's'}, classified from arm structure.
        <span className="mt-0.5 block text-ink-faint">
          Over the {formatCount(data.n_scanned)} trials scanned
          {data.n_total !== null && data.n_total > data.n_scanned && (
            <> of {formatCount(data.n_total)} total</>
          )}
          , matched by drug name (ClinicalTrials.gov keys by intervention text), so a broad set.
        </span>
        {data.n_ambiguous > 0 && (
          <span className="mt-0.5 block text-ink-faint" data-testid="combinations-ambiguous">
            {formatCount(data.n_ambiguous)} further multi-drug trial
            {data.n_ambiguous === 1 ? '' : 's'} had no arm-level drug assignment and were excluded —
            not guessed.
          </span>
        )}
      </p>

      <ExampleList
        noun="combinations"
        hint="drugs given together"
        total={data.n_combination}
        testid="combination-examples"
        joiner=" + "
        examples={data.combination_examples}
      />
      <ExampleList
        noun="comparisons"
        hint="drugs tested against each other"
        total={data.n_comparison}
        testid="comparison-examples"
        joiner=" vs "
        examples={data.comparison_examples}
      />

      <div className="mt-3 text-right">
        <CitationChip fact={fact} />
      </div>
    </>
  )
}

function ExampleList({
  noun,
  hint,
  total,
  testid,
  joiner,
  examples,
}: {
  noun: string
  hint: string
  total: number
  testid: string
  joiner: string
  examples: CombinationExample[]
}) {
  if (examples.length === 0) return null
  return (
    <div className="mt-3">
      {/* Explicitly an excerpt: name the shown count AND the total, so a few example rows can
          never be read as the whole (the summary's count is the population, this is the sample). */}
      <p className="mb-1 text-[11px] font-medium text-ink-faint" data-testid={`${testid}-heading`}>
        Examples — {formatCount(examples.length)} of {formatCount(total)} {noun}{' '}
        <span className="font-normal">({hint})</span>
      </p>
      <ul className="space-y-0.5" data-testid={testid}>
        {examples.map((e) => (
          <li key={e.nct_id} className="flex items-center gap-2 text-xs">
            <a
              href={`https://clinicaltrials.gov/study/${e.nct_id}`}
              target="_blank"
              rel="noreferrer"
              className="shrink-0 font-mono text-[11px] text-accent hover:underline"
            >
              {e.nct_id}
            </a>
            <span className="text-ink-muted">{e.drugs.join(joiner)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
