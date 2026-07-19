import { Link } from 'react-router-dom'
import { Card } from './Card'

/**
 * The drugs in OUR catalog that act on this target, joined on the stable Ensembl id (never the
 * alias-prone symbol). This is a catalog membership, not a sourced fact -- so it carries no
 * provenance chip and no FactGate: an empty list is an honest "no such drug in our catalog",
 * which is NOT "undruggable" (the world's answer lives on the cancer landscape's drugged flag).
 *
 * Labels are ChEMBL ids: the catalog join returns ids, not names, and each is a live link into
 * the drug's brief where its name and evidence live.
 */
export function CatalogDrugsCard({ id, drugs }: { id?: string; drugs: string[] }) {
  return (
    <Card id={id} title="Drugs in the catalog" note="Drugs we hold that act on this target">
      {drugs.length === 0 ? (
        <p className="text-sm text-ink-faint">
          No drug in our catalog acts on this target. That is a gap in our catalog, not a claim
          that the target is undruggable.
        </p>
      ) : (
        <ul className="flex flex-wrap gap-2" data-testid="catalog-drugs">
          {drugs.map((chemblId) => (
            <li key={chemblId}>
              <Link
                to={`/drugs/${chemblId}`}
                data-testid="catalog-drug-link"
                className="rounded-md border border-line bg-surface px-2 py-1 font-mono text-xs text-accent hover:underline"
                title="Open this drug's brief"
              >
                {chemblId}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
