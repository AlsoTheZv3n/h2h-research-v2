import type { Epidemiology, SourcedFact } from '../../api/types'
import { formatCount } from '../../format'
import { Card } from '../ui/Card'
import { CitationChip } from '../ui/CitationChip'
import { FactGate } from '../ui/FactGate'
import { ResolvedSection } from '../ui/ResolvedSection'

/**
 * Block A: European mortality for a cancer (Eurostat).
 *
 * The age-standardised death rate (ASR) is the honest cross-country-comparable figure, so the
 * card is ASR bars by country (sorted, Switzerland highlighted) plus headline figures. Deaths,
 * not incidence; a rate, never in a doughnut. Honest states run through FactGate + the
 * match-type layer: an outage is amber, unmapped is "not available for this cancer", a rollup
 * names the broader entity.
 */
export function EpidemiologyCard({
  id,
  facts,
  cancerName,
}: {
  id?: string
  facts?: SourcedFact[]
  cancerName: string
}) {
  return (
    <Card id={id} title="Epidemiology" note="European mortality · Eurostat">
      <FactGate facts={facts}>
        {(fact) => (
          <ResolvedSection<Epidemiology>
            fact={fact}
            cancerName={cancerName}
            emptyLabel="No European mortality figures for this cancer"
          >
            {(epi) => <EpidemiologyBody epi={epi} fact={fact} />}
          </ResolvedSection>
        )}
      </FactGate>
    </Card>
  )
}

function Figure({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-faint">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums text-ink">
        {value} <span className="text-xs font-normal text-ink-faint">{unit}</span>
      </dd>
    </div>
  )
}

function EpidemiologyBody({ epi, fact }: { epi: Epidemiology; fact: SourcedFact }) {
  const max = Math.max(...epi.by_country.map((c) => c.asr), 1)
  return (
    <>
      <dl className="mb-3 flex flex-wrap gap-x-8 gap-y-2">
        <Figure label="EU" value={epi.eu_asr !== null ? String(epi.eu_asr) : '—'} unit="per 100k" />
        <Figure
          label="Switzerland"
          value={epi.ch_asr !== null ? String(epi.ch_asr) : '—'}
          unit="per 100k"
        />
        {epi.total_deaths !== null && (
          <Figure label="EU deaths" value={formatCount(epi.total_deaths)} unit={`in ${epi.year}`} />
        )}
      </dl>

      <p className="mb-2 text-[11px] text-ink-faint">
        Age-standardised mortality rate — deaths, not incidence — per 100 000 · Eurostat{' '}
        {epi.year}
      </p>

      <div className="space-y-1" data-testid="epi-bars">
        {epi.by_country.map((c) => {
          const isCH = c.geo === 'CH'
          return (
            <div key={c.geo} data-testid="epi-bar" className="flex items-center gap-2 text-xs">
              <span
                className={`w-28 shrink-0 truncate ${isCH ? 'font-medium text-accent' : 'text-ink-muted'}`}
              >
                {c.country}
              </span>
              <div className="h-2 flex-1 rounded bg-surface">
                <div
                  className={`h-2 rounded ${isCH ? 'bg-accent' : 'bg-ink-faint'}`}
                  style={{ width: `${(c.asr / max) * 100}%` }}
                />
              </div>
              <span className="w-10 shrink-0 text-right tabular-nums text-ink-muted">{c.asr}</span>
            </div>
          )
        })}
      </div>

      <div className="mt-2 text-right">
        <CitationChip fact={fact} />
      </div>
    </>
  )
}
