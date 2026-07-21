import { render, screen, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { AlterationFrequency, SourcedFact } from '../api/types'
import { AlterationFrequencyCard } from './AlterationFrequencyCard'

/**
 * The card must keep four states visibly apart, or it re-commits the founding None-vs-0 bug:
 * a real % (measured), a real 0% (measured_zero, "profiled, never mutated"), a gene it could not
 * join (gene_unmapped, "not measured"), and a whole cancer with no cohort (unmapped). It must also
 * label the SCOPE (mutation-only) so the number is never read as the full alteration frequency, and
 * carry the cBioPortal attribution (the licence condition).
 */

function renderCard(props: ComponentProps<typeof AlterationFrequencyCard>) {
  return render(
    <MemoryRouter>
      <AlterationFrequencyCard {...props} />
    </MemoryRouter>,
  )
}

function fact(value: AlterationFrequency | null, over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value,
    status: 'ok',
    source: 'cbioportal',
    source_url: 'https://www.cbioportal.org/study/summary?id=skcm_tcga_pan_can_atlas_2018',
    retrieved_at: '2026-07-21T12:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

const measured: AlterationFrequency = {
  state: 'measured',
  study_id: 'skcm_tcga_pan_can_atlas_2018',
  study_label: 'Cutaneous Melanoma — TCGA PanCancer Atlas',
  study_name: 'Skin Cutaneous Melanoma (TCGA, PanCancer Atlas)',
  alteration_scope: 'somatic mutation (SNV/indel); excludes copy-number & fusions',
  denominator_type: 'samples with mutation data (sequenced)',
  denominator_n: 440,
  genes: [
    { symbol: 'BRAF', ensembl_id: 'ENSG00000157764', entrez_id: 673, state: 'measured', altered_n: 233, pct: 53.0 },
    { symbol: 'TP53', ensembl_id: 'ENSG00000141510', entrez_id: 7157, state: 'measured_zero', altered_n: 0, pct: 0.0 },
    { symbol: 'MYSTERY', ensembl_id: 'ENSG_X', entrez_id: null, state: 'gene_unmapped' },
  ],
  attribution: {
    portal: [
      'Cerami E, et al. The cBio Cancer Genomics Portal. Cancer Discov. 2012;2(5):401-404.',
      'Gao J, et al. Sci Signal. 2013;6(269):pl1.',
      'de Bruijn I, et al. Cancer Res. 2023;83(23):3861-3867.',
    ],
    study_citation: 'TCGA, Cell 2018',
    study_pmid: '29625048',
  },
}

describe('AlterationFrequencyCard', () => {
  it('shows measured %, a distinct measured-zero, and a distinct gene_unmapped', () => {
    renderCard({ facts: [fact(measured)] })

    // A real measured frequency, as a percentage.
    expect(screen.getByText('53.0%')).toBeInTheDocument()

    // measured_zero renders as a 0% (with a "none" marker), NOT as "not measured".
    const zero = screen.getByTestId('alteration-measured-zero')
    expect(zero.textContent).toContain('0.0%')

    // gene_unmapped renders "not measured" — the distinct, non-zero state.
    const unmapped = screen.getByTestId('alteration-gene-unmapped')
    expect(unmapped.textContent).toMatch(/not measured/i)

    // The two must not be confused: the 0% row is NOT the not-measured element.
    expect(zero).not.toBe(unmapped)
  })

  it('labels the scope (mutation-only) so the number is not read as full alteration frequency', () => {
    renderCard({ facts: [fact(measured)] })
    const scope = screen.getByTestId('alteration-scope')
    expect(scope.textContent).toMatch(/somatic mutation/i)
    expect(scope.textContent).toMatch(/floor/i) // stated as a floor on the true frequency
  })

  it('carries the cBioPortal attribution and the source study (the licence condition)', () => {
    renderCard({ facts: [fact(measured)] })
    const attribution = screen.getByTestId('alteration-attribution')
    expect(within(attribution).getByText(/Cerami/)).toBeInTheDocument()
    expect(attribution.textContent).toContain('TCGA, Cell 2018')
    expect(within(attribution).getByRole('link', { name: /PMID 29625048/ })).toHaveAttribute(
      'href',
      'https://pubmed.ncbi.nlm.nih.gov/29625048/',
    )
    expect(attribution.textContent).toMatch(/ODC Open Database License|ODbL/)
  })

  it('orders measured genes first (by frequency) and never-joined genes last', () => {
    renderCard({ facts: [fact(measured)] })
    const rows = screen.getAllByTestId('alteration-row')
    const symbols = rows.map((r) => within(r).getByText(/BRAF|TP53|MYSTERY/).textContent)
    expect(symbols[0]).toBe('BRAF') // highest measured frequency first
    expect(symbols[symbols.length - 1]).toBe('MYSTERY') // gene_unmapped sinks to the end
  })

  it('renders "no matched cohort" for an unmapped cancer — never a zero', () => {
    renderCard({ facts: [fact({ state: 'unmapped' })] })
    const note = screen.getByTestId('alteration-unmapped')
    expect(note.textContent).toMatch(/no matched cBioPortal cohort/i)
    expect(note.textContent).toMatch(/not measured/i)
    // No gene rows and no fabricated 0%.
    expect(screen.queryByTestId('alteration-genes')).not.toBeInTheDocument()
  })

  it('renders a source_failed outage as an amber chip, never as "no mutations"', () => {
    renderCard({ facts: [fact(null, { status: 'source_failed', error: 'cBioPortal 503' })] })
    expect(screen.queryByTestId('alteration-genes')).not.toBeInTheDocument()
    expect(screen.queryByText(/0\.0%/)).not.toBeInTheDocument()
  })
})
