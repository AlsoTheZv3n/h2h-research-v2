"""Runner: probe every source for every seed drug, assemble a coverage table,
save raw JSON, write a CSV and an RDKit SVG.

Run:  uv sync  &&  uv run python probe.py
(Run it locally -- the external APIs are not reachable from every sandbox.)"""
from __future__ import annotations
import json
import time
from pathlib import Path

import httpx
import pandas as pd
from dotenv import load_dotenv

from adapters import (ChEMBLAdapter, ClinicalTrialsAdapter,
                      OpenTargetsAdapter, PubMedAdapter)
from drugs import SEED_DRUGS

load_dotenv()

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

try:
    from rdkit import Chem
    from rdkit.Chem.Draw import rdMolDraw2D
    _RDKIT = True
except Exception:  # noqa: BLE001
    _RDKIT = False

class RetryTransport(httpx.HTTPTransport):
    """Retry transient upstream failures with exponential backoff.

    Lives in the transport, not the adapters: these sources rate-limit bursts
    (ClinicalTrials.gov answers 403 to rapid sequential queries) and ChEMBL's
    /activity intermittently 500s or stalls. Without this the probe reports a
    source outage as a coverage gap -- the one answer it must never give.
    """

    # 403 is deliberately absent: ClinicalTrials.gov's 403 is a deterministic WAF
    # verdict on the User-Agent, not a transient fault. Retrying it burns backoff
    # and buries the cause.
    RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

    def __init__(self, *args, attempts: int = 4, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.attempts = attempts

    def handle_request(self, request):  # type: ignore[override]
        last_exc: Exception | None = None
        response = None
        for attempt in range(self.attempts):
            last_exc, response = None, None
            try:
                response = super().handle_request(request)
                if response.status_code not in self.RETRY_STATUS:
                    return response
                response.read()
                response.close()
            except httpx.TimeoutException as exc:
                last_exc = exc
            if attempt < self.attempts - 1:
                time.sleep(2 ** attempt)  # 1s, 2s, 4s
        if last_exc is not None:
            raise last_exc
        return response  # exhausted retries: hand back the last failing response


# ClinicalTrials.gov sits behind a WAF that allowlists known client tokens and 403s
# everything else -- a bare "h2h-experiment/0.1 (research spike)" is rejected, and so
# is "Mozilla/5.0" and "curl/8.0.1". Keeping the python-httpx token satisfies it while
# still identifying this spike to the other sources. Verified against all four.
USER_AGENT = f"python-httpx/{httpx.__version__} (h2h-experiment/0.1; research spike)"


def build_client() -> httpx.Client:
    return httpx.Client(
        # 120s, not 30s: ChEMBL /activity legitimately takes 30-60s per molecule,
        # and a timeout there is indistinguishable from "this drug has no IC50s".
        timeout=120.0,
        follow_redirects=True,
        transport=RetryTransport(attempts=4),
        headers={"User-Agent": USER_AGENT},
    )


def smiles_is_valid(smiles: str | None) -> bool:
    if not smiles:
        return False
    if _RDKIT:
        return Chem.MolFromSmiles(smiles) is not None
    return True  # rdkit missing: can only confirm a string is present


def render_first_structure(rows: list[dict]) -> None:
    if not _RDKIT:
        return
    for row in rows:
        smiles = row.get("smiles")
        if not smiles:
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        d = rdMolDraw2D.MolDraw2DSVG(320, 240)
        d.DrawMolecule(mol)
        d.FinishDrawing()
        name = row["drug"].replace(" ", "_")
        (OUT / f"structure_{name}.svg").write_text(d.GetDrawingText())
        print(f"  rendered structure SVG for {row['drug']}")
        return


def main() -> None:
    client = build_client()
    adapters = [ChEMBLAdapter(client), ClinicalTrialsAdapter(client),
                OpenTargetsAdapter(client), PubMedAdapter(client)]

    rows: list[dict] = []
    for drug in SEED_DRUGS:
        print(f"probing: {drug}")
        records = {a.name: a.fetch(drug) for a in adapters}

        raw = {name: rec.as_dict() for name, rec in records.items()}
        (OUT / f"raw_{drug.replace(' ', '_')}.json").write_text(json.dumps(raw, indent=2))

        ch = records["chembl"].fields
        ct = records["clinicaltrials"].fields
        ot = records["opentargets"].fields
        pm = records["pubmed"].fields

        rows.append({
            "drug": drug,
            # chembl_id/pref_name are in the table on purpose: molecule search ranks
            # by structure, so the wrong compound resolving is invisible without them.
            "chembl_id": ch.get("chembl_id"),
            "chembl_pref_name": ch.get("chembl_pref_name"),
            "smiles": ch.get("smiles"),
            "smiles_valid": smiles_is_valid(ch.get("smiles")),
            "mw": ch.get("mw"),
            "alogp": ch.get("alogp"),
            # Deliberately not `or 0`: None means the source failed, 0 means it
            # answered "none". Collapsing them prints an outage as a data finding.
            "n_ic50": ch.get("n_ic50"),
            "chembl_moa": ch.get("moa"),
            "n_trials": ct.get("n_trials"),
            "max_phase": ct.get("max_phase"),
            "has_terminated": ct.get("has_terminated"),
            "ot_drug_type": ot.get("drug_type"),
            "ot_max_stage": ot.get("max_stage"),
            "ot_n_indications": ot.get("n_indications"),
            "n_pubmed": pm.get("n_pubmed", 0),
            "errors": "; ".join(f"{n}:{r.error}" for n, r in records.items() if r.error) or None,
        })

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "coverage.csv", index=False)

    with pd.option_context("display.max_columns", None, "display.width", 200):
        print("\n=== coverage table ===")
        print(df.drop(columns=["smiles"]).to_string(index=False))

    n = len(df)
    print("\n=== can the data carry the product? ===")
    print(f"  SMILES present/valid : {int(df['smiles_valid'].sum())}/{n}")
    print(f"  IC50 activities      : {int((df['n_ic50'] > 0).sum())}/{n}")
    print(f"  clinical trials      : {int((df['n_trials'] > 0).sum())}/{n}")
    print(f"  mechanism of action  : {int(df['chembl_moa'].notna().sum())}/{n}")
    print(f"  PubMed hits          : {int((df['n_pubmed'] > 0).sum())}/{n}")

    # Without this the counts above read as findings about the data even when a
    # source was simply down -- the one wrong answer this spike must never give.
    n_err = int(df["errors"].notna().sum())
    if n_err:
        print(f"\n  !! {n_err}/{n} rows hit a source error -- the counts above are")
        print("     a FLOOR, not a finding. Read the errors column before trusting them.")

    render_first_structure(rows)

    print(f"\noutputs in: {OUT}")
    client.close()


if __name__ == "__main__":
    main()
