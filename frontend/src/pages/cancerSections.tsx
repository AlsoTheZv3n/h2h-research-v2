import type { ReactNode } from 'react'
import type { CancerDetail } from '../api/types'
import { EpidemiologyCard } from '../components/EpidemiologyCard'
import { PipelineCard } from '../components/PipelineCard'
import { SurvivalCard } from '../components/SurvivalCard'
import { TargetLandscapeCard } from '../components/TargetLandscapeCard'

/**
 * One content section of the cancer detail page.
 *
 * This registry is the single source of truth for section ORDER, nav LABEL, anchor ID and
 * how it RENDERS. The page maps over it to build the stack, the section nav, and the error
 * boundaries; nothing else decides what sections exist. A later block (epidemiology,
 * survival) is added by appending one entry here -- it then appears in the page, in the nav,
 * and inside its own error boundary and anchor, with no other wiring.
 *
 * `id` is a stable hand-authored slug, not a generated id: it is the URL anchor
 * (/cancers/MONDO_x#pipeline), so it must be human, stable and unique.
 */
export interface CancerSection {
  id: string
  label: string
  render: (d: CancerDetail) => ReactNode
}

export const CANCER_SECTIONS: CancerSection[] = [
  {
    id: 'pipeline',
    label: 'Pipeline',
    render: (d) => (
      <PipelineCard id="pipeline" facts={d.facts['pipeline']} catalogDrugIds={d.catalog_drug_ids} />
    ),
  },
  {
    id: 'target-landscape',
    label: 'Target landscape',
    render: (d) => (
      <TargetLandscapeCard
        id="target-landscape"
        facts={d.facts['target_landscape']}
        catalogDrugByTarget={d.target_catalog_drug}
      />
    ),
  },
  {
    id: 'epidemiology',
    label: 'Epidemiology',
    render: (d) => (
      <EpidemiologyCard id="epidemiology" facts={d.facts['epidemiology']} cancerName={d.name} />
    ),
  },
  {
    id: 'survival',
    label: 'Survival',
    render: (d) => <SurvivalCard id="survival" facts={d.facts['survival']} cancerName={d.name} />,
  },
]
