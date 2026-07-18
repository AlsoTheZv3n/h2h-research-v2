"""Phase 0 data spike: Open Targets Platform GraphQL (KEY: opentargets).

THROWAWAY probe. No app code. Measures whether a disease-centric
"target landscape" evidence block would render POPULATED per cancer, and whether
the disease spine is usable to seed an oncology catalog.

Open access, no key, no login. Uses only the Python stdlib (urllib + json) so it
adds zero dependencies. Run:  python probe.py

Contract discipline (see backend/ingestion/base.py): None != 0. A missing figure is
"not measured", never zero. Coverage here = would the block render with real data.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error

ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"

# The 5 cancers as handed to the spike (old EFO IDs) and the canonical current IDs.
# Every one of the 5 EFO IDs returns disease:null against the live platform today;
# each resolves to a MONDO id that lists the old EFO id in obsoleteTerms + dbXRefs.
# This map is what we VERIFY below, not an assumption.
CANCERS = [
    ("NSCLC", "EFO_0003060", "MONDO_0005233"),
    ("breast carcinoma", "EFO_0000305", "MONDO_0004989"),
    ("pancreatic carcinoma", "EFO_0002618", "MONDO_0005192"),
    ("melanoma", "EFO_0000756", "MONDO_0005105"),
    ("chronic myeloid leukemia (CML)", "EFO_0000339", "MONDO_0011996"),
]

CANCER_ROOT = "MONDO_0004992"  # "cancer" -- catalog seed (descendants)

Q_DISEASE = """
query D($id: String!) {
  disease(efoId: $id) { id name obsoleteTerms }
}
"""

Q_SPINE = """
query Spine($id: String!) {
  disease(efoId: $id) { id name isTherapeuticArea descendants }
}
"""

# Target landscape: top associated targets + association score + per-evidence-type
# scores (datatypeScores) + per-target tractability buckets (modality SM/AB/...).
Q_LANDSCAPE = """
query L($id: String!) {
  disease(efoId: $id) {
    id
    name
    associatedTargets(page: {index: 0, size: 25}) {
      count
      rows {
        score
        datatypeScores { id score }
        target {
          id
          approvedSymbol
          tractability { label modality value }
        }
      }
    }
  }
}
"""


def gql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    if payload.get("errors"):
        raise RuntimeError("; ".join(e.get("message", "") for e in payload["errors"]))
    return payload["data"]


def tractability_summary(rows: list) -> dict:
    """How many of the top targets carry at least one tractability bucket, and how
    many are small-molecule OR antibody tractable (the drugged/undrugged signal)."""
    with_any = 0
    sm_or_ab = 0
    for row in rows:
        tr = (row.get("target") or {}).get("tractability") or []
        if tr:
            with_any += 1
        if any(t.get("value") and t.get("modality") in ("SM", "AB") for t in tr):
            sm_or_ab += 1
    return {"with_any": with_any, "sm_or_ab": sm_or_ab, "n": len(rows)}


def main() -> None:
    print("=" * 72)
    print("PART A -- disease spine / ID drift")
    print("=" * 72)

    # A.1 every provided EFO id must be probed against the live source
    for label, efo, mondo in CANCERS:
        try:
            d = gql(Q_DISEASE, {"id": efo}).get("disease")
        except Exception as exc:  # noqa: BLE001
            d = f"ERROR: {exc}"
        print(f"  disease(efoId={efo!r}) [{label}] -> {d}")

    print()
    # A.2 canonical MONDO resolves + lists old EFO in obsoleteTerms
    for label, efo, mondo in CANCERS:
        d = gql(Q_DISEASE, {"id": mondo}).get("disease") or {}
        obs = d.get("obsoleteTerms") or []
        print(
            f"  {mondo} -> name={d.get('name')!r} | "
            f"old {efo} in obsoleteTerms: {efo in obs}"
        )

    print()
    # A.3 catalog enumeration seed
    spine = gql(Q_SPINE, {"id": CANCER_ROOT}).get("disease") or {}
    desc = spine.get("descendants") or []
    print(
        f"  catalog seed {CANCER_ROOT} name={spine.get('name')!r} "
        f"isTherapeuticArea={spine.get('isTherapeuticArea')} "
        f"descendants={len(desc)}"
    )

    print()
    print("=" * 72)
    print("PART B -- target landscape coverage (POPULATED / EMPTY per cancer)")
    print("=" * 72)
    results = []
    for label, efo, mondo in CANCERS:
        try:
            d = gql(Q_LANDSCAPE, {"id": mondo}).get("disease") or {}
        except Exception as exc:  # noqa: BLE001
            print(f"\n  {label} [{mondo}] -> SOURCE_FAILED: {exc}")
            results.append((label, None))
            continue
        at = d.get("associatedTargets") or {}
        count = at.get("count")
        rows = at.get("rows") or []
        # scores sane? all in [0,1] and top row non-trivial
        scores = [r.get("score") for r in rows if r.get("score") is not None]
        sane = bool(scores) and all(0.0 <= s <= 1.0 for s in scores)
        top = rows[0] if rows else None
        top_sym = (top.get("target") or {}).get("approvedSymbol") if top else None
        top_score = top.get("score") if top else None
        n_evidence = len(top.get("datatypeScores") or []) if top else 0
        tr = tractability_summary(rows)
        populated = bool(count) and bool(rows) and sane and tr["with_any"] > 0
        results.append((label, {
            "count": count, "top_sym": top_sym, "top_score": top_score,
            "n_evidence_types": n_evidence, "scores_sane": sane, "tract": tr,
            "populated": populated,
        }))
        print(f"\n  {label} [{mondo}] name={d.get('name')!r}")
        print(f"    associatedTargets.count = {count}  (rows fetched: {len(rows)})")
        print(f"    top target = {top_sym}  score = {top_score}")
        print(f"    evidence types on top target = {n_evidence}")
        print(f"    scores sane (0..1) = {sane}")
        print(
            f"    tractability: {tr['with_any']}/{tr['n']} top targets carry buckets, "
            f"{tr['sm_or_ab']}/{tr['n']} SM/AB-tractable"
        )
        print(f"    => {'POPULATED' if populated else 'EMPTY'}")

    print()
    print("=" * 72)
    print("COVERAGE SUMMARY")
    print("=" * 72)
    pop = 0
    for label, r in results:
        if r is None:
            print(f"  {label:32s} SOURCE_FAILED (not measured)")
            continue
        if r["populated"]:
            pop += 1
        tr = r["tract"]
        print(
            f"  {label:32s} {'POPULATED' if r['populated'] else 'EMPTY':10s} "
            f"count={r['count']}, top={r['top_sym']}({r['top_score']:.3f}), "
            f"evTypes={r['n_evidence_types']}, tract={tr['with_any']}/{tr['n']}"
        )
    print(f"\n  POPULATED: {pop}/{len(CANCERS)}")


if __name__ == "__main__":
    main()
