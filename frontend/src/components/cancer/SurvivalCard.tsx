import type { SourcedFact, Survival } from '../../api/types'
import { formatCount } from '../../format'
import { Card } from '../ui/Card'
import { CitationChip } from '../ui/CitationChip'
import { FactGate } from '../ui/FactGate'
import { ResolvedSection } from '../ui/ResolvedSection'

/**
 * Block B: 5-year RELATIVE survival by stage (SEER, U.S. registries).
 *
 * A table of stage-specific rates with their 95% CI, case count and share of cases -- NOT a
 * Kaplan-Meier curve, and with no traffic-light colouring (a survival rate is not a verdict).
 * Solid tumours are staged (Localized / Regional / Distant, the SEER summary stage, not TNM);
 * leukemias are not stage-decomposed, so only the all-stages figure shows -- a real EMPTY for
 * the stage block, never a zero. Honest states run through FactGate + the match-type layer.
 */
export function SurvivalCard({
  id,
  facts,
  cancerName,
}: {
  id?: string
  facts?: SourcedFact[]
  cancerName: string
}) {
  return (
    <Card id={id} title="Survival" note="5-year relative survival · SEER (U.S.)">
      <FactGate facts={facts}>
        {(fact) => (
          <ResolvedSection<Survival>
            fact={fact}
            cancerName={cancerName}
            emptyLabel="No survival figures for this cancer"
          >
            {(surv) => <SurvivalBody surv={surv} fact={fact} />}
          </ResolvedSection>
        )}
      </FactGate>
    </Card>
  )
}

const pct = (x: number) => `${x.toFixed(1)}%`

function SurvivalBody({ surv, fact }: { surv: Survival; fact: SourcedFact }) {
  const all = surv.all_stages
  // The CI and the case count are independent: a capped rate (~100%) suppresses the CI bounds
  // but the total N is still meaningful, so build the two parts separately and never let a null
  // CI take the case count down with it.
  const ci =
    all.ci_low !== null && all.ci_high !== null ? `95% CI ${pct(all.ci_low)}–${pct(all.ci_high)}` : null
  const cases = all.n !== null ? `${formatCount(all.n)} cases` : null
  return (
    <>
      <p className="flex flex-wrap items-baseline gap-x-1.5">
        <span className="text-2xl font-semibold tabular-nums text-ink" data-testid="survival-all">
          {pct(all.rate)}
        </span>
        <span className="text-sm text-ink-muted">5-year relative survival, all stages</span>
        <CitationChip fact={fact} />
      </p>
      {(ci || cases) && (
        <p className="mt-0.5 text-xs text-ink-faint">{[ci, cases].filter(Boolean).join(' · ')}</p>
      )}

      {surv.staged ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[26rem] text-left text-xs" data-testid="survival-table">
            <thead>
              <tr className="border-b border-line text-ink-faint">
                <th className="py-1 pr-2 font-medium">Stage at diagnosis</th>
                <th className="py-1 pr-2 font-medium">5-yr relative survival</th>
                <th className="py-1 pr-2 font-medium">95% CI</th>
                <th className="py-1 pr-2 font-medium">Cases</th>
                <th className="py-1 font-medium">Share</th>
              </tr>
            </thead>
            <tbody>
              {surv.by_stage.map((s) => (
                <tr
                  key={s.stage}
                  data-testid="survival-row"
                  className="border-b border-line last:border-b-0"
                >
                  <td className="py-1 pr-2 text-ink">{s.stage}</td>
                  <td className="py-1 pr-2 tabular-nums text-ink">{pct(s.rate)}</td>
                  <td className="py-1 pr-2 tabular-nums text-ink-muted">
                    {s.ci_low !== null && s.ci_high !== null
                      ? `${pct(s.ci_low)}–${pct(s.ci_high)}`
                      : '—'}
                  </td>
                  <td className="py-1 pr-2 tabular-nums text-ink-muted">
                    {s.n !== null ? formatCount(s.n) : '—'}
                  </td>
                  <td className="py-1 tabular-nums text-ink-muted">
                    {s.share !== null ? `${(s.share * 100).toFixed(0)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p data-testid="survival-not-staged" className="mt-2 text-xs text-ink-muted">
          Not broken down by stage — leukemias are not assigned the summary-stage schema, so only
          the all-stages figure is available (a real gap, not zero).
        </p>
      )}

      <p className="mt-2 text-[11px] text-ink-faint">
        Relative survival (against a matched general population), not overall survival · SEER
        summary stage, not TNM · a table of stage-specific rates, not a Kaplan–Meier curve · U.S.
        SEER registries
      </p>
    </>
  )
}
