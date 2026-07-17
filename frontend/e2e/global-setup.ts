import { execFileSync } from 'node:child_process'

/**
 * Seeds one drug whose ChEMBL mechanism fetch failed.
 *
 * The E2E has to prove that a `source_failed` fact survives DB → API → UI and lands
 * as a red "unavailable" chip rather than as "nothing found". That state used to be
 * supplied for free by ChEMBL falling over, which made the test a coin flip: green
 * when the source was sick, red when it was healthy. Both readings were noise.
 *
 * So the row is written directly into the real Postgres. This is not a mock: the API
 * reads it, serves it and the browser renders it through the whole stack. The only
 * thing being controlled is *which* drug is broken, not whether the pipeline works.
 *
 * The drug is fictitious (CHEMBL_E2E_FAILURE) so it cannot collide with a real one,
 * and teardown removes it.
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
    throw new Error(
      'Could not seed the E2E fixture. The compose stack must be up ' +
        '(`docker compose up`) before running these tests.\n' +
        String((e as { stderr?: Buffer }).stderr ?? e),
    )
  }
}
