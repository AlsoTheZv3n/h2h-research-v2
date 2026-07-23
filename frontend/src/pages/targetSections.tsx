import type { ReactNode } from 'react'
import type { TargetDetail } from '../api/types'
import { AssociatedCancersCard } from '../components/target/AssociatedCancersCard'
import { CatalogDrugsCard } from '../components/target/CatalogDrugsCard'
import { ExtractedRelationsCard } from '../components/target/ExtractedRelationsCard'
import { TargetAlterationCard } from '../components/target/TargetAlterationCard'

/**
 * One content section of the target detail page. The single source of truth for section ORDER,
 * nav LABEL, anchor ID and how it RENDERS -- the target-side twin of cancerSections. The page
 * maps over it to build the stack, the nav and the error boundaries; a later block is one entry
 * appended here.
 *
 * `id` is a stable hand-authored slug -- it is the URL anchor (/targets/ENSG_x#associated-cancers).
 */
export interface TargetSection {
  id: string
  label: string
  render: (d: TargetDetail) => ReactNode
}

export const TARGET_SECTIONS: TargetSection[] = [
  {
    id: 'associated-cancers',
    label: 'Associated cancers',
    render: (d) => (
      <AssociatedCancersCard id="associated-cancers" facts={d.facts['associated_cancers']} />
    ),
  },
  // #43: the transpose of the cancer page's mutation-frequency block -- for this gene, how often it
  // is mutated in each cancer it drives (cBioPortal). Sits under the associated cancers it augments.
  {
    id: 'mutation-frequency',
    label: 'Mutation frequency',
    render: (d) => (
      <TargetAlterationCard
        id="mutation-frequency"
        facts={d.facts['target_alteration_frequency']}
      />
    ),
  },
  {
    id: 'catalog-drugs',
    label: 'Drugs in the catalog',
    render: (d) => <CatalogDrugsCard id="catalog-drugs" drugs={d.catalog_drugs} />,
  },
  // #44: machine-EXTRACTED relations from the literature (PubTator). LAST on purpose -- it is a
  // different, lower-confidence KIND of evidence (extracted, not curated), so it sits below the
  // curated cards and wears a distinct frame, never blended with them.
  {
    id: 'extracted-relations',
    label: 'Extracted relations',
    render: (d) => (
      <ExtractedRelationsCard id="extracted-relations" facts={d.facts['extracted_relations']} />
    ),
  },
]
