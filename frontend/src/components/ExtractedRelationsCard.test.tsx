import { render, screen, within } from '@testing-library/react'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { ExtractedRelations, SourcedFact } from '../api/types'
import { ExtractedRelationsCard } from './ExtractedRelationsCard'

/**
 * The one thing this card must never fail: a reader can tell at a glance that these are EXTRACTED,
 * not curated. So the tests assert the banner, the co-mention framing (volume, not evidence), the
 * link only where a disease bridged to our catalog, and the gene_unmapped honest state.
 */

function renderCard(props: ComponentProps<typeof ExtractedRelationsCard>) {
  return render(
    <MemoryRouter>
      <ExtractedRelationsCard {...props} />
    </MemoryRouter>,
  )
}

function fact(value: ExtractedRelations | null, over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value,
    status: 'ok',
    source: 'pubtator',
    source_url: 'https://www.ncbi.nlm.nih.gov/research/pubtator3/',
    retrieved_at: '2026-07-21T12:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

const extracted: ExtractedRelations = {
  state: 'extracted',
  provenance: 'extracted, not curated — PubTator3, NLP over the literature',
  diseases: [
    { name: 'Carcinoma Non Small Cell Lung', rel_type: 'associate', co_mentions: 10913, mondo_id: 'MONDO_0005233', mondo_label: 'NSCLC' },
    { name: 'Neoplasms', rel_type: 'associate', co_mentions: 12134, mondo_id: null, mondo_label: null },
  ],
  chemicals: [
    { name: 'Gefitinib', rel_type: 'negative_correlate', co_mentions: 3188 },
  ],
  n_disease_relations: 2551,
  n_chemical_relations: 4556,
  attribution: 'PubTator3, courtesy of the U.S. National Library of Medicine. Wei C-H, et al.',
}

describe('ExtractedRelationsCard', () => {
  it('leads with the "extracted, not curated" banner and co-mention framing', () => {
    renderCard({ facts: [fact(extracted)] })
    const banner = screen.getByTestId('extracted-banner')
    expect(banner.textContent).toMatch(/extracted, not curated/i)
    expect(banner.textContent).toMatch(/not verified facts/i)
    // The count is framed as co-mentions (attention), never as evidence weight.
    expect(banner.textContent).toMatch(/co-mentions/i)
    // The whole block is visually set apart from the curated cards.
    expect(screen.getByTestId('extracted-frame')).toBeInTheDocument()
  })

  it('links a disease that bridged to our catalog, and leaves an unbridged one unlinked', () => {
    renderCard({ facts: [fact(extracted)] })
    const diseases = screen.getByTestId('extracted-diseases')
    // NSCLC bridged (mondo_id) -> a link into the catalog.
    expect(within(diseases).getByRole('link', { name: /Non Small Cell Lung/ })).toHaveAttribute(
      'href',
      '/cancers/MONDO_0005233',
    )
    // Neoplasms did not bridge -> plain text, never a dead link.
    expect(within(diseases).queryByRole('link', { name: 'Neoplasms' })).not.toBeInTheDocument()
    expect(within(diseases).getByText('Neoplasms')).toBeInTheDocument()
  })

  it('shows chemicals with their relation type and co-mention count', () => {
    renderCard({ facts: [fact(extracted)] })
    const chems = screen.getByTestId('extracted-chemicals')
    expect(within(chems).getByText('Gefitinib')).toBeInTheDocument()
    expect(chems.textContent).toMatch(/negatively correlated/i)
    expect(chems.textContent).toMatch(/3,188 co-mentions/)
  })

  it('renders gene_unmapped as an honest not-joined state, not an empty list', () => {
    renderCard({ facts: [fact({ state: 'gene_unmapped' })] })
    expect(screen.getByTestId('extracted-gene-unmapped').textContent).toMatch(/could not be matched/i)
    expect(screen.queryByTestId('extracted-frame')).not.toBeInTheDocument()
  })
})
