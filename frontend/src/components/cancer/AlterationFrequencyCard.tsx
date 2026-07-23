import { Link } from 'react-router-dom'
import type { AlterationFrequency, AlterationGene, SourcedFact } from '../../api/types'
import { Card } from '../ui/Card'
import { CitationChip } from '../ui/CitationChip'
import { FactGate } from '../ui/FactGate'

/**
 * Block E: how often each landscape gene is somatically MUTATED in a matched tumour cohort
 * (cBioPortal, TCGA PanCancer Atlas) — an orthogonal, quantitative signal beside the Open Targets
 * association score. Issue #43.
 *
 * Honest states, kept visibly distinct, because the founding bug is one careless collapse away:
 *   unmapped       no curated cohort for this cancer (most of the catalog) — a coverage gap, said
 *                  plainly, NEVER rendered as "0% altered".
 *   measured       a real percentage, with the cohort, the SCOPE and the denominator beside it.
 *   measured_zero  profiled but never mutated — a real 0%, distinct from "not measured".
 *   gene_unmapped  a gene we could not join to a cBioPortal id — not measured, not a zero.
 *
 * SCOPE is stated on the card, not buried: this is somatic mutations only (SNV/indel), a FLOOR on
 * the true alteration frequency (copy-number and fusions are excluded), so the number is never read
 * as more than it is. Attribution (the ODbL grant condition) is carried on the surface.
 */
export function AlterationFrequencyCard({ id, facts }: { id?: string; facts?: SourcedFact[] }) {
  return (
    <Card
      id={id}
      title="Mutation frequency"
      note="How often each landscape gene is mutated in a matched tumour cohort · cBioPortal (TCGA)"
    >
      <FactGate facts={facts}>
        {(fact) => {
          const value = fact.value as AlterationFrequency | null
          if (!value || value.state === 'unmapped') {
            // NOT_MEASURED: no matched cohort. The coverage ceiling, said plainly — never a zero.
            return (
              <p className="text-sm text-ink-faint" data-testid="alteration-unmapped">
                No matched cBioPortal cohort for this cancer. Mutation frequency is available only
                for the tumour types with a curated TCGA cohort (~two dozen major cancers); for the
                rest it is <span className="italic">not measured</span> — which is not zero.
                <CitationChip fact={fact} />
              </p>
            )
          }
          return <AlterationFrequencyBody value={value} fact={fact} />
        }}
      </FactGate>
    </Card>
  )
}

// Measured rows first (by descending frequency), then the genes we could not join. A stable,
// honest order: the reader sees the most-mutated drivers first, and "not measured" never masquerades
// as a low frequency by sorting among the real numbers.
function sortGenes(genes: AlterationGene[]): AlterationGene[] {
  const rank = (g: AlterationGene) => (g.state === 'gene_unmapped' ? -1 : (g.pct ?? 0))
  return [...genes].sort((a, b) => {
    if (a.state === 'gene_unmapped' && b.state !== 'gene_unmapped') return 1
    if (b.state === 'gene_unmapped' && a.state !== 'gene_unmapped') return -1
    return rank(b) - rank(a)
  })
}

function AlterationFrequencyBody({ value, fact }: { value: AlterationFrequency; fact: SourcedFact }) {
  const genes = sortGenes(value.genes ?? [])
  const max = Math.max(...genes.map((g) => g.pct ?? 0), 1)
  const attribution = value.attribution

  return (
    <>
      <p className="mb-1 text-xs text-ink-muted">
        In the <span className="font-medium text-ink">{value.study_label}</span>
        {typeof value.denominator_n === 'number' && (
          <> cohort (n={value.denominator_n} {value.denominator_type})</>
        )}
        .
      </p>
      {/* SCOPE, stated so the number is never read as the full alteration frequency. */}
      <p className="mb-3 text-[11px] text-ink-faint" data-testid="alteration-scope">
        {value.alteration_scope} — a floor on the true alteration frequency.
      </p>

      <ul className="divide-y divide-line" data-testid="alteration-genes">
        {genes.map((g) => (
          <li
            key={g.symbol}
            data-testid="alteration-row"
            className="flex items-center gap-2 py-1.5 text-sm"
          >
            <span className="w-16 shrink-0 font-medium">
              {g.ensembl_id ? (
                <Link
                  to={`/targets/${g.ensembl_id}`}
                  className="text-accent hover:underline"
                  title="Open this target's page"
                >
                  {g.symbol}
                </Link>
              ) : (
                <span className="text-ink">{g.symbol}</span>
              )}
            </span>
            <GeneReading gene={g} max={max} />
          </li>
        ))}
      </ul>

      {attribution && (
        <details className="mt-3 text-[11px] text-ink-faint" data-testid="alteration-attribution">
          <summary className="cursor-pointer text-ink-muted">Data &amp; attribution</summary>
          <p className="mt-1">
            {/* The specific source study (ODbL requires it beside the portal citations). */}
            Source cohort: {value.study_name ?? value.study_label}
            {attribution.study_citation && <> — {attribution.study_citation}</>}
            {attribution.study_pmid && (
              <>
                {' '}
                <a
                  href={`https://pubmed.ncbi.nlm.nih.gov/${attribution.study_pmid}/`}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-accent underline underline-offset-2"
                >
                  PMID {attribution.study_pmid}
                </a>
              </>
            )}
            .
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4">
            {attribution.portal.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <p className="mt-1">
            cBioPortal data is under the ODC Open Database License (ODbL); attribution required.
          </p>
        </details>
      )}

      <div className="mt-2 text-right">
        <CitationChip fact={fact} />
      </div>
    </>
  )
}

/** One gene's reading: a bar + % for a measured frequency, a distinct faint "0%" for a measured
 *  zero, and a distinct "not measured" for a gene we could not join. The three never blur. */
function GeneReading({ gene, max }: { gene: AlterationGene; max: number }) {
  if (gene.state === 'gene_unmapped') {
    return (
      <span
        className="text-[11px] text-ink-faint italic"
        data-testid="alteration-gene-unmapped"
        title="Could not join this gene to a cBioPortal (Entrez) id — not measured, not zero."
      >
        not measured
      </span>
    )
  }
  const pct = gene.pct ?? 0
  const isZero = gene.state === 'measured_zero' || pct === 0
  return (
    <span className="flex flex-1 items-center gap-2">
      <span className="h-2 flex-1 rounded bg-surface">
        <span
          className={`block h-2 rounded ${isZero ? 'bg-transparent' : 'bg-accent'}`}
          style={{ width: `${(pct / max) * 100}%` }}
        />
      </span>
      <span
        className={`w-24 shrink-0 text-right text-xs tabular-nums ${isZero ? 'text-ink-faint' : 'text-ink'}`}
        title={
          isZero
            ? 'Profiled in this cohort, never mutated — a measured 0%, not "not measured".'
            : `${gene.altered_n} of the cohort's samples carry a mutation in ${gene.symbol}.`
        }
        data-testid={isZero ? 'alteration-measured-zero' : 'alteration-measured'}
      >
        {pct.toFixed(1)}%{isZero && <span className="ml-1 text-ink-faint">· none</span>}
      </span>
    </span>
  )
}
