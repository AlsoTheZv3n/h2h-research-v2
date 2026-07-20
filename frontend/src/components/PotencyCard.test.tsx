import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SelectivityProfile, SourcedFact } from '../api/types'
import { BriefStateProvider } from './Fact'
import { PotencyCard } from './PotencyCard'

/**
 * The card answers one question from the ranking alone: what does the drug mainly target, and
 * how selectively? So the tests assert the reader can read that off it -- the reference, the
 * selective-vs-multi-target verdict against the disclosed 100× rule, targets ranked with the
 * beyond-threshold ones visibly incidental -- and that the honest states never collapse (an
 * outage is not "no potency", a single-measurement target is disclosed, not silently ranked).
 */

function fact(over: Partial<SourcedFact> = {}): SourcedFact {
  return {
    value: null,
    status: 'ok',
    source: 'chembl',
    source_url: 'https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL3353410/',
    retrieved_at: '2026-07-20T00:00:00Z',
    error: null,
    confidence: null,
    ...over,
  }
}

function target(over: Partial<SelectivityProfile['targets'][number]>) {
  return {
    target_chembl_id: 'CHEMBL0',
    target_pref_name: 'Target',
    median_nm: 10,
    n: 5,
    fold_vs_reference: 1,
    is_target: true,
    ...over,
  }
}

// Osimertinib-shaped: EGFR is the reference, LSD1 sits far beyond 100× (incidental).
const selective: SelectivityProfile = {
  reference: target({ target_chembl_id: 'CHEMBL203', target_pref_name: 'Epidermal growth factor receptor', median_nm: 8.8, n: 151, fold_vs_reference: 1, is_target: true }),
  targets: [
    target({ target_chembl_id: 'CHEMBL203', target_pref_name: 'Epidermal growth factor receptor', median_nm: 8.8, n: 151, fold_vs_reference: 1, is_target: true }),
    target({ target_chembl_id: 'CHEMBL6136', target_pref_name: 'Lysine-specific histone demethylase 1A', median_nm: 3980, n: 3, fold_vs_reference: 451.9, is_target: false }),
  ],
  n_targets: 1,
  n_measured_targets: 2,
  threshold_fold: 100,
  n_protein_rows: 154,
  n_excluded_rows: 540,
  n_uncorroborated_targets: 7,
}

// Imatinib-shaped: several targets within 100× of PDGFRα -> multi-target.
const multiTarget: SelectivityProfile = {
  reference: target({ target_chembl_id: 'CHEMBL2007', target_pref_name: 'Platelet-derived growth factor receptor alpha', median_nm: 18, n: 5, fold_vs_reference: 1, is_target: true }),
  targets: [
    target({ target_chembl_id: 'CHEMBL2007', target_pref_name: 'Platelet-derived growth factor receptor alpha', median_nm: 18, n: 5, fold_vs_reference: 1, is_target: true }),
    target({ target_chembl_id: 'CHEMBL1936', target_pref_name: 'Mast/stem cell growth factor receptor Kit', median_nm: 58, n: 12, fold_vs_reference: 3.22, is_target: true }),
    target({ target_chembl_id: 'CHEMBL1862', target_pref_name: 'Tyrosine-protein kinase ABL1', median_nm: 200, n: 23, fold_vs_reference: 11.1, is_target: true }),
  ],
  n_targets: 3,
  n_measured_targets: 3,
  threshold_fold: 100,
  n_protein_rows: 40,
  n_excluded_rows: 916,
  n_uncorroborated_targets: 11,
}

describe('PotencyCard', () => {
  it('leads with a "Selective" verdict naming the reference, against the disclosed 100× rule', () => {
    render(<PotencyCard facts={[fact({ value: selective })]} isBiologic={false} />)
    const verdict = screen.getByTestId('selectivity-verdict')
    expect(verdict).toHaveTextContent('Selective')
    // The reader can state what it mainly targets and how selective, from this line alone. The
    // reference name appears both here and in its ranked row -> assert on the verdict paragraph.
    expect(verdict.closest('p')).toHaveTextContent('Epidermal growth factor receptor')
    expect(screen.getByText(/no other target within 100× of it/)).toBeInTheDocument()
  })

  it('reads "Multi-target" with the count when several targets fall within 100×', () => {
    render(<PotencyCard facts={[fact({ value: multiTarget })]} isBiologic={false} />)
    expect(screen.getByTestId('selectivity-verdict')).toHaveTextContent('Multi-target')
    expect(screen.getByText(/3 targets within 100× of it/)).toBeInTheDocument()
  })

  it('ranks the targets and marks beyond-threshold ones as incidental, not real targets', () => {
    render(<PotencyCard facts={[fact({ value: selective })]} isBiologic={false} />)
    const rows = screen.getAllByTestId('selectivity-row')
    expect(rows).toHaveLength(2)
    // Reference first, labelled "ref"; the beyond-threshold target shows its fold, faded.
    expect(within(rows[0]).getByText('ref')).toBeInTheDocument()
    expect(within(rows[1]).getByText('452×')).toBeInTheDocument()
    // The two bars are visually distinct: a real-target bar and an incidental one. Style them
    // alike and the "what is a target" distinction the card exists for silently disappears.
    expect(screen.getByTestId('bar-target')).toBeInTheDocument()
    expect(screen.getByTestId('bar-incidental')).toBeInTheDocument()
    expect(screen.getByTestId('bar-target').className).not.toEqual(
      screen.getByTestId('bar-incidental').className,
    )
  })

  it('discloses the ranking rule and the set-aside counts, never hiding them', () => {
    render(<PotencyCard facts={[fact({ value: selective })]} isBiologic={false} />)
    const note = screen.getByTestId('selectivity-setaside')
    expect(note).toHaveTextContent('most potent = reference, within 100× = a target')
    expect(note).toHaveTextContent('7 measured once (not ranked)')
    expect(note).toHaveTextContent('540 rows set aside')
  })

  it('a profile with nothing corroborated says WHY, not a bare "no data"', () => {
    const empty: SelectivityProfile = {
      reference: null,
      targets: [],
      n_targets: 0,
      n_measured_targets: 0,
      threshold_fold: 100,
      n_protein_rows: 0,
      n_excluded_rows: 0,
      n_uncorroborated_targets: 2,
    }
    render(<PotencyCard facts={[fact({ value: empty })]} isBiologic={false} />)
    expect(screen.getByTestId('selectivity-empty')).toHaveTextContent(
      /measured only once — too few to rank/,
    )
    expect(screen.queryByTestId('selectivity-profile')).not.toBeInTheDocument()
  })

  it('renders an outage as a calm unavailable chip, never "no potency"', () => {
    render(
      <PotencyCard
        facts={[fact({ value: null, status: 'source_failed', error: 'boom' })]}
        isBiologic={false}
      />,
    )
    expect(screen.getByTestId('fact-source-failed')).toBeInTheDocument()
    expect(screen.queryByTestId('selectivity-profile')).not.toBeInTheDocument()
    expect(screen.queryByTestId('selectivity-verdict')).not.toBeInTheDocument()
  })

  it('says "waiting for sources" while enriching, but "not collected" once ready', () => {
    // The founding bug: a card that branches on fact presence alone tells every drug on first
    // open -- before anything is measured -- that the measurement came back empty.
    const { rerender } = render(
      <BriefStateProvider value="enriching">
        <PotencyCard facts={undefined} isBiologic={false} />
      </BriefStateProvider>,
    )
    expect(screen.getByTestId('fact-pending')).toBeInTheDocument()
    expect(screen.queryByTestId('fact-not-collected')).not.toBeInTheDocument()

    rerender(
      <BriefStateProvider value="ready">
        <PotencyCard facts={undefined} isBiologic={false} />
      </BriefStateProvider>,
    )
    expect(screen.getByTestId('fact-not-collected')).toBeInTheDocument()
  })

  it('is not applicable to a biologic, named honestly, not a blanket "biologic"', () => {
    // The prop is really !is_small_molecule -- true for oligonucleotides and Unknown-typed drugs,
    // which are not antibodies/ADCs. The message must not misstate them as "biologic".
    render(<PotencyCard facts={undefined} isBiologic={true} />)
    const na = screen.getByTestId('not-applicable')
    expect(na).toHaveTextContent(/not a small molecule/i)
    expect(na).not.toHaveTextContent(/biologic/i)
    expect(screen.queryByTestId('selectivity-profile')).not.toBeInTheDocument()
  })
})
