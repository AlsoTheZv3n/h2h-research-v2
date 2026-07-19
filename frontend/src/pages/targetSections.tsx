import type { ReactNode } from 'react'
import type { TargetDetail } from '../api/types'
import { AssociatedCancersCard } from '../components/AssociatedCancersCard'
import { CatalogDrugsCard } from '../components/CatalogDrugsCard'

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
  {
    id: 'catalog-drugs',
    label: 'Drugs in the catalog',
    render: (d) => <CatalogDrugsCard id="catalog-drugs" drugs={d.catalog_drugs} />,
  },
]
