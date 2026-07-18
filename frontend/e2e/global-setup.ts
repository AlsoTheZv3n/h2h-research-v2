import { execFileSync } from 'node:child_process'

/**
 * Seeds the two drug states the E2E cannot get reliably any other way.
 *
 * CHEMBL_E2E_FAILURE -- a drug whose ChEMBL mechanism fetch failed. The suite has to
 * prove a `source_failed` fact survives DB → API → UI and lands as a red
 * "unavailable" chip rather than "nothing found". That state used to be supplied for
 * free by ChEMBL falling over, which made the test a coin flip: green when the source
 * was sick, red when it was healthy. Both readings were noise.
 *
 * CHEMBL_E2E_UNSEEN -- in the catalog, zero facts, last_enriched_at NULL. The
 * chat must refuse to put a model in front of it: handed no evidence, a model answers
 * from training. No real drug stays in this state once anyone opens it, so it has to
 * be seeded.
 *
 * The rows are written directly into the real Postgres. This is not a mock: the API
 * reads them, serves them and the browser renders them through the whole stack. The
 * only thing controlled is *which* drug is in which state, not whether the pipeline
 * works.
 *
 * Both IDs are fictitious so they cannot collide with a real ChEMBL id. They are NOT
 * removed afterwards -- this comment claimed a teardown that has never existed, which
 * is a small lie in a file about not telling them. They persist in the dev database
 * and show up in the catalog; two synthetic rows beside ~3,900 real ones is a price
 * worth paying for a deterministic suite, and now it is stated rather than implied
 * away.
 */

const SQL = `
INSERT INTO drug (chembl_id, pref_name, drug_type, max_phase, primary_target, smiles,
                  maturity, last_enriched_at)
VALUES ('CHEMBL_E2E_FAILURE', 'E2E FIXTURE DRUG', 'Small molecule', 4, 'E2E',
        'CCO', 'partial', now())
ON CONFLICT (chembl_id) DO UPDATE SET last_enriched_at = now();

INSERT INTO fact (drug_chembl_id, key, source, value, status, source_url, retrieved_at, error)
VALUES ('CHEMBL_E2E_FAILURE', 'moa', 'chembl', NULL, 'source_failed',
        'https://www.ebi.ac.uk/chembl/', now(),
        'mechanism: 500 Internal Server Error'),
       ('CHEMBL_E2E_FAILURE', 'n_trials', 'clinicaltrials', '0'::jsonb, 'empty',
        'https://clinicaltrials.gov/', now(), NULL)
ON CONFLICT (drug_chembl_id, key, source) DO UPDATE
   SET status = excluded.status, value = excluded.value, error = excluded.error;

-- A drug nobody has ever looked at: in the catalog, zero facts, never enriched.
-- The chat must refuse to ask a model about it, because a model handed no context
-- answers from training. last_enriched_at stays NULL -- that is what "nobody looked"
-- means, and it is a different row state from "we looked and found nothing".
--
-- The evidence is deleted first, because the row persists between runs and "unseen"
-- is a claim about the whole row, not about one column. Resetting only
-- last_enriched_at while facts or abstract links survived from an earlier run would
-- leave a drug that is documented as having no evidence and demonstrably has some --
-- the test would pass or fail depending on what ran before it, which is the property
-- a fixture exists to remove.
DELETE FROM fact WHERE drug_chembl_id = 'CHEMBL_E2E_UNSEEN';
DELETE FROM drug_abstract WHERE drug_chembl_id = 'CHEMBL_E2E_UNSEEN';

INSERT INTO drug (chembl_id, pref_name, drug_type, max_phase, maturity,
                  last_enriched_at, literature_fetched_at)
VALUES ('CHEMBL_E2E_UNSEEN', 'E2E NEVER LOOKED', 'Small molecule', 1,
        'index_only', NULL, NULL)
ON CONFLICT (chembl_id) DO UPDATE
   SET last_enriched_at = NULL, literature_fetched_at = NULL;

-- Cancer catalog fixtures. The cancer overview e2e needs a real, filterable catalog,
-- but CI seeds only the drug demo fixture, so the Open-Targets-loaded cancer table is
-- empty there and every cancer test would probe nothing. Two drugged cancers and one
-- with no drug programme, so the has_drugs facet has something to narrow -- the same
-- reason the source_failed drug fixture is seeded rather than waited for. Idempotent,
-- last_enriched_at NULL (never analyzed); they persist beside the real catalog in dev.
INSERT INTO cancer (disease_id, name, therapeutic_area, n_drugs, n_targets, last_enriched_at)
VALUES
  ('MONDO_E2E_NSCLC',  'E2E lung carcinoma',   'respiratory or thoracic disease',       500, 8000, now()),
  ('MONDO_E2E_BREAST', 'E2E breast carcinoma', 'reproductive system or breast disease', 400, 9000, NULL),
  ('MONDO_E2E_RARE',   'E2E rare tumor',       'hematologic disorder',                    0,   12, NULL)
ON CONFLICT (disease_id) DO UPDATE
   SET name = excluded.name, therapeutic_area = excluded.therapeutic_area,
       n_drugs = excluded.n_drugs, n_targets = excluded.n_targets,
       last_enriched_at = excluded.last_enriched_at;

-- MONDO_E2E_NSCLC is the ENRICHED fixture: it carries a target-landscape brief so the
-- cancer detail e2e renders the real card without a live Open Targets fetch (a never-
-- enriched cancer would trigger one on open). The other two stay not-analyzed.
INSERT INTO cancer_fact (disease_id, key, source, value, status, source_url, retrieved_at)
VALUES ('MONDO_E2E_NSCLC', 'target_landscape', 'opentargets',
        '[{"symbol":"EGFR","score":0.89,"evidence_types":["clinical","somatic_mutation"],"sm_tractable":true,"ab_tractable":true},
          {"symbol":"KRAS","score":0.83,"evidence_types":["clinical"],"sm_tractable":true,"ab_tractable":false}]'::jsonb,
        'ok', 'https://platform.opentargets.org/disease/MONDO_E2E_NSCLC', now()),
       ('MONDO_E2E_NSCLC', 'pipeline', 'opentargets',
        '{"total":3,"by_phase":[
           {"stage":"APPROVAL","count":2,"drugs":[{"chembl_id":"CHEMBL_E2E_INPIPE","name":"E2E APPROVED DRUG"},{"chembl_id":"CHEMBL_E2E_EXTERNAL","name":"E2E EXTERNAL DRUG"}]},
           {"stage":"PHASE_2","count":1,"drugs":[{"chembl_id":"CHEMBL_E2E_CAND","name":"E2E CANDIDATE"}]}]}'::jsonb,
        'ok', 'https://platform.opentargets.org/disease/MONDO_E2E_NSCLC', now())
ON CONFLICT (disease_id, key, source) DO UPDATE
   SET value = excluded.value, status = excluded.status, retrieved_at = excluded.retrieved_at;

-- A drug the pipeline names, seeded so it is in the catalog and therefore linkable; the
-- other two pipeline drugs are NOT seeded, so the page shows them as plain text -- the
-- exact-id, never-by-name linkability the weave requires, checked end to end.
INSERT INTO drug (chembl_id, pref_name, drug_type, max_phase, maturity)
VALUES ('CHEMBL_E2E_INPIPE', 'E2E APPROVED DRUG', 'Small molecule', 4, 'index_only')
ON CONFLICT (chembl_id) DO UPDATE SET pref_name = excluded.pref_name;
`

function psql(sql: string): void {
  execFileSync(
    'docker',
    ['compose', 'exec', '-T', 'postgres', 'psql', '-U', 'h2h', '-d', 'h2h', '-c', sql],
    { cwd: '..', stdio: 'pipe' },
  )
}

export default function globalSetup(): void {
  try {
    psql(SQL)
  } catch (e) {
    // Lead with what psql actually said, and offer the likely cause as a guess
    // rather than a diagnosis. The first version asserted "the compose stack must be
    // up" -- and the first time it fired, the stack was up and the real problem was
    // a chembl_id one character past varchar(20). An error that names the wrong
    // cause is worse than one that names none: it sends the reader to check
    // something that was never broken.
    throw new Error(
      'Seeding the E2E fixtures failed. psql said:\n' +
        String((e as { stderr?: Buffer }).stderr ?? e) +
        '\n\nIf that looks like a connection problem, the compose stack needs to be ' +
        'up (`docker compose up`) before these tests run.',
    )
  }
}
