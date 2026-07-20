import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { SourcedFact } from '../api/types'
import { BriefStateProvider } from './Fact'
import { TargetLandscapeCard } from './TargetLandscapeCard'

/**
 * The card must never render an Open Targets outage as "no associated targets" -- that
 * would tell a reader a cancer has no druggable biology when the source was merely down.
 * And the R4 flag adds a second load-bearing distinction: `unknown` (not measured) and
 * `unexploited` (measured, no drug) must never render alike -- the None-vs-0 lie one level up.
 *
 * Every symbol is now a link to its target page, so every render needs a router.
 */

function renderCard(props: ComponentProps<typeof TargetLandscapeCard>) {
  return render(
    <MemoryRouter>
      <TargetLandscapeCard {...props} />
    </MemoryRouter>,
  )
}

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'opentargets',
    source_url: 'https://platform.opentargets.org/disease/MONDO_0005233',
    retrieved_at: '2026-07-18T18:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

// One target per drugged state, so a single fixture exercises all four badges + the filter.
const landscape = {
  threshold: 0.5,
  n_strong: 4,
  targets: [
    { symbol: 'EGFR', ensembl_id: 'ENSG_E', score: 0.89, evidence_types: ['clinical', 'somatic_mutation'], sm_tractable: true, ab_tractable: true, drug_status: 'approved' },
    { symbol: 'TP53', ensembl_id: 'ENSG_T', score: 0.83, evidence_types: ['clinical'], sm_tractable: true, ab_tractable: false, drug_status: 'clinical' },
    { symbol: 'STK11', ensembl_id: 'ENSG_S', score: 0.74, evidence_types: ['somatic_mutation'], sm_tractable: false, ab_tractable: false, drug_status: 'unexploited' },
    { symbol: 'DICER1', ensembl_id: 'ENSG_D', score: 0.72, evidence_types: ['literature'], sm_tractable: false, ab_tractable: false, drug_status: 'unknown' },
  ],
}

describe('TargetLandscapeCard', () => {
  it('renders the targets with their provenance chip', () => {
    renderCard({ facts: [fact({ value: landscape })] })
    expect(screen.getByTestId('target-landscape')).toBeInTheDocument()
    expect(screen.getByText('EGFR')).toBeInTheDocument()
    expect(screen.getByText('STK11')).toBeInTheDocument()
    expect(screen.getByTestId('source-info')).toBeInTheDocument()
  })

  it('renders each drugged state with its own distinct marker', () => {
    renderCard({ facts: [fact({ value: landscape })] })
    const states = ['approved', 'clinical', 'unexploited', 'unknown']
    for (const s of states) expect(screen.getByTestId(`drug-status-${s}`)).toBeInTheDocument()
    // Distinct by more than the testid (which is derived from the status, so it can't
    // collapse): the four must render with four distinct CLASSES (colours) and four distinct
    // LABELS. Style two alike (e.g. clinical coloured like approved) or label two the same
    // and this goes red -- the tautology the testid-only check would have missed.
    const classes = states.map((s) => screen.getByTestId(`drug-status-${s}`).className)
    expect(new Set(classes).size).toBe(4)
    const labels = states.map((s) => screen.getByTestId(`drug-status-${s}`).textContent)
    expect(new Set(labels).size).toBe(4)
    // And the two whose confusion matters most read as different words -- and the finding's
    // label WRITES OUT the claim ("no drug anywhere") rather than the term of art "unexploited",
    // which the harness read as "not in this catalog" (the opposite). "not measured" is not "no
    // drug". The scope word ("anywhere") is what stops catalog-absence being read as the finding.
    expect(screen.getByTestId('drug-status-unexploited')).toHaveTextContent('no drug anywhere')
    expect(screen.getByTestId('drug-status-unknown')).toHaveTextContent('not measured')
    expect(screen.getByTestId('drug-status-unexploited')).not.toHaveTextContent('unexploited')
  })

  it('a target with no drug_status (pre-flag fact) reads unknown, never unexploited', () => {
    const preFlag = {
      threshold: 0.5,
      n_strong: 1,
      // No drug_status key at all -- the shape of a fact stored before the flag shipped.
      targets: [{ symbol: 'FOO', ensembl_id: 'ENSG_F', score: 0.8, evidence_types: [], sm_tractable: false, ab_tractable: false }],
    }
    renderCard({ facts: [fact({ value: preFlag })] })
    expect(screen.getByTestId('drug-status-unknown')).toBeInTheDocument()
    // The load-bearing line: "we haven't measured it" must not read as "no drug exists".
    expect(screen.queryByTestId('drug-status-unexploited')).not.toBeInTheDocument()
  })

  it('the status filter narrows to "unexploited only"', async () => {
    const user = userEvent.setup()
    renderCard({ facts: [fact({ value: landscape })] })
    expect(screen.getAllByTestId('landscape-row')).toHaveLength(4)
    await user.selectOptions(screen.getByTestId('landscape-filter-status'), 'unexploited')
    const rows = screen.getAllByTestId('landscape-row')
    expect(rows).toHaveLength(1)
    expect(within(rows[0]).getByText('STK11')).toBeInTheDocument()
  })

  it('links every target symbol to its own target page, by Ensembl id', () => {
    renderCard({ facts: [fact({ value: landscape })] })
    const links = screen.getAllByTestId('landscape-target-link')
    expect(links).toHaveLength(4) // every displayed target is drillable
    const egfr = links.find((l) => l.textContent === 'EGFR')
    expect(egfr).toHaveAttribute('href', '/targets/ENSG_E') // joined on the stable Ensembl id
  })

  it('links to a catalog drug with a WORDED action label, not a bare glyph', () => {
    renderCard({ facts: [fact({ value: landscape })], catalogDrugByTarget: { ENSG_E: 'CHEMBL_EGFR' } })
    // EGFR (ENSG_E) is the only target we hold a drug for -> one link into that brief.
    const link = screen.getByTestId('landscape-catalog-link')
    expect(link).toHaveAttribute('href', '/drugs/CHEMBL_EGFR')
    expect(screen.getAllByTestId('landscape-catalog-link')).toHaveLength(1)
    // The harness read the old bare ℞ as a drugged-status marker. The link must carry a visible
    // word so it reads as an action, not a status.
    expect(link).toHaveTextContent(/in catalog/i)
    expect(link).not.toHaveTextContent('℞')
  })

  it('a drugged target with no catalog drug shows its status but no ℞ link', () => {
    // EGFR is `approved` in the fact but absent from our catalog map: it must read
    // "approved, no link". Catalog absence is a missing link, never the drugged status --
    // and never "unexploited", the world's answer, which the fact still supplies.
    renderCard({ facts: [fact({ value: landscape })], catalogDrugByTarget: {} })
    expect(screen.queryByTestId('landscape-catalog-link')).not.toBeInTheDocument()
    expect(screen.getByTestId('drug-status-approved')).toBeInTheDocument()
    // The symbol still drills into the target page even with no catalog drug.
    expect(screen.getAllByTestId('landscape-target-link').length).toBeGreaterThan(0)
  })

  it('still renders targets from a pre-reshape (bare array) fact value', () => {
    renderCard({ facts: [fact({ value: landscape.targets })] })
    expect(screen.getByTestId('target-landscape')).toBeInTheDocument()
    expect(screen.getByText('EGFR')).toBeInTheDocument()
    expect(screen.getByText('STK11')).toBeInTheDocument()
  })

  it('renders an outage as a calm unavailable chip, never "no targets"', () => {
    renderCard({ facts: [fact({ value: null, status: 'source_failed', error: 'boom' })] })
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByTestId('target-landscape')).not.toBeInTheDocument()
    expect(screen.queryByText(/no associated targets/i)).not.toBeInTheDocument()
  })

  it('renders a real empty as "no associated targets"', () => {
    renderCard({ facts: [fact({ value: {}, status: 'empty' })] })
    expect(screen.getByText(/no associated targets/i)).toBeInTheDocument()
    expect(screen.queryByTestId('target-landscape')).not.toBeInTheDocument()
  })

  it('says "waiting for sources" while the brief is still enriching', () => {
    render(
      <MemoryRouter>
        <BriefStateProvider value="enriching">
          <TargetLandscapeCard facts={undefined} />
        </BriefStateProvider>
      </MemoryRouter>,
    )
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
  })
})
