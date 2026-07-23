import type { ReactNode } from 'react'
import type { CancerDetail } from '../api/types'
import { AlterationFrequencyCard } from '../components/cancer/AlterationFrequencyCard'
import { EpidemiologyCard } from '../components/cancer/EpidemiologyCard'
import { PipelineCard } from '../components/cancer/PipelineCard'
import { SurvivalCard } from '../components/cancer/SurvivalCard'
import { TargetLandscapeCard } from '../components/cancer/TargetLandscapeCard'
import { TrialRealityCard } from '../components/cancer/TrialRealityCard'

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
 *
 * ORDER is the demotion discipline (C4): a block earns its place by feeding a conclusion, so the
 * synthesis's evidence leads and inert decoration sinks. The block -> conclusion map:
 *
 *   target-landscape  -> the druggable-biology + unexploited-opportunity statements, and the TDL
 *                        verdicts (C1/C3). The richest decision source -> first.
 *   pipeline          -> the crowded-vs-sparse-field statement (C1).
 *   trial-reality     -> the notable-attrition statement (C1).
 *   survival          -> the outcomes-hinge-on-stage statement + the prognosis read (C1).
 *   epidemiology      -> NO synthesis statement: mortality-by-geography is context, not a
 *                        therapeutic or druggability decision for this tool. DEMOTED to last --
 *                        kept (nothing sourced is deleted; its honest states stand), just not
 *                        allowed to sit above the blocks a reader actually acts on.
 */
export interface CancerSection {
  id: string
  label: string
  render: (d: CancerDetail) => ReactNode
}

export const CANCER_SECTIONS: CancerSection[] = [
  {
    id: 'target-landscape',
    label: 'Target landscape',
    render: (d) => (
      <TargetLandscapeCard
        id="target-landscape"
        facts={d.facts['target_landscape']}
        catalogDrugByTarget={d.target_catalog_drug}
        targetTdl={d.target_tdl}
      />
    ),
  },
  // #43: mutation frequency sits directly under the landscape it augments -- the reader sees, for
  // each associated target, how often it is actually mutated in a matched cohort (the orthogonal
  // signal beside the association score). cBioPortal, EXACT-match cohorts only; honest states.
  {
    id: 'mutation-frequency',
    label: 'Mutation frequency',
    render: (d) => (
      <AlterationFrequencyCard
        id="mutation-frequency"
        facts={d.facts['alteration_frequency']}
      />
    ),
  },
  {
    id: 'pipeline',
    label: 'Pipeline',
    render: (d) => (
      <PipelineCard id="pipeline" facts={d.facts['pipeline']} catalogDrugIds={d.catalog_drug_ids} />
    ),
  },
  {
    id: 'trial-reality',
    label: 'Trial reality',
    render: (d) => <TrialRealityCard id="trial-reality" facts={d.facts['trial_reality']} />,
  },
  {
    id: 'survival',
    label: 'Survival',
    render: (d) => <SurvivalCard id="survival" facts={d.facts['survival']} cancerName={d.name} />,
  },
  // Demoted (C4): feeds no synthesis statement -- context, not a decision. Last, never deleted.
  {
    id: 'epidemiology',
    label: 'Epidemiology',
    render: (d) => (
      <EpidemiologyCard id="epidemiology" facts={d.facts['epidemiology']} cancerName={d.name} />
    ),
  },
]
