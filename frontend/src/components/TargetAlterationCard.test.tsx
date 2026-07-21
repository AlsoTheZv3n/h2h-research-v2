import { render, screen, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { SourcedFact, TargetAlterationFrequency } from '../api/types'
import { TargetAlterationCard } from './TargetAlterationCard'

/**
 * The target-side reflection must keep its states apart: measured, a real 0% (measured_zero), a
 * cohort outage (source_failed, amber — not a zero), and the two whole-fact gaps no_cohort /
 * gene_unmapped. It must label the scope (mutation-only) and carry attribution.
 */

function renderCard(props: ComponentProps<typeof TargetAlterationCard>) {
  return render(
    <MemoryRouter>
      <TargetAlterationCard {...props} />
    </MemoryRouter>,
  )
}

function fact(value: TargetAlterationFrequency | null, over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value,
    status: 'ok',
    source: 'cbioportal',
    source_url: 'https://www.cbioportal.org/',
    retrieved_at: '2026-07-21T12:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

const measured: TargetAlterationFrequency = {
  state: 'measured',
  entrez_id: 673,
  alteration_scope: 'somatic mutation (SNV/indel); excludes copy-number & fusions',
  cancers: [
    { disease_id: 'MONDO_0005075', name: 'papillary thyroid carcinoma', study_label: 'Thyroid — TCGA', state: 'measured', pct: 58.6, altered_n: 287, denominator_n: 490 },
    { disease_id: 'MONDO_0005012', name: 'cutaneous melanoma', study_label: 'Melanoma — TCGA', state: 'measured', pct: 53.0, altered_n: 233, denominator_n: 440 },
    { disease_id: 'MONDO_0007256', name: 'hepatocellular carcinoma', study_label: 'HCC — TCGA', state: 'measured_zero', pct: 0.0, altered_n: 0, denominator_n: 366 },
    { disease_id: 'MONDO_0018874', name: 'acute myeloid leukemia', study_label: 'AML — TCGA', state: 'source_failed' },
  ],
  n_more: 0,
  attribution: { portal: ['Cerami E, et al. Cancer Discov. 2012.', 'Gao J, et al. Sci Signal. 2013.', 'de Bruijn I, et al. Cancer Res. 2023.'] },
}

describe('TargetAlterationCard', () => {
  it('shows a measured %, a distinct measured-zero, and a distinct cohort outage', () => {
    renderCard({ facts: [fact(measured)] })
    expect(screen.getByText('58.6%')).toBeInTheDocument()

    const zero = screen.getByTestId('target-alt-zero')
    expect(zero.textContent).toContain('0.0%')

    const failed = screen.getByTestId('target-alt-cohort-failed')
    expect(failed.textContent).toMatch(/unavailable/i)
    // The 0% and the outage must never be the same element.
    expect(zero).not.toBe(failed)
  })

  it('orders measured cancers by frequency and sinks a cohort outage to the end', () => {
    renderCard({ facts: [fact(measured)] })
    const rows = screen.getAllByTestId('target-alt-row')
    const names = rows.map((r) => within(r).getByRole('link').textContent)
    expect(names[0]).toBe('papillary thyroid carcinoma') // highest
    expect(names[names.length - 1]).toBe('acute myeloid leukemia') // source_failed last
  })

  it('labels the scope and carries the cBioPortal attribution', () => {
    renderCard({ facts: [fact(measured)] })
    expect(screen.getByTestId('target-alt-scope').textContent).toMatch(/somatic mutation/i)
    const attribution = screen.getByTestId('target-alt-attribution')
    expect(within(attribution).getByText(/Cerami/)).toBeInTheDocument()
    expect(attribution.textContent).toMatch(/ODC Open Database License|ODbL/)
  })

  it('renders no_cohort and gene_unmapped as distinct not-measured states, never a zero', () => {
    const { unmount } = renderCard({ facts: [fact({ state: 'no_cohort' })] })
    expect(screen.getByTestId('target-alt-no-cohort').textContent).toMatch(/not measured/i)
    expect(screen.queryByTestId('target-alt-cancers')).not.toBeInTheDocument()
    unmount()

    renderCard({ facts: [fact({ state: 'gene_unmapped' })] })
    expect(screen.getByTestId('target-alt-gene-unmapped').textContent).toMatch(/not measured/i)
  })
})
