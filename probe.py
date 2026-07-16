"""Runner: probe every source for every seed drug, assemble a coverage table,
save raw JSON, write a CSV, optionally a ydata-profiling report and an RDKit SVG.

Run:  uv sync  &&  uv run python probe.py
(Run it locally -- the external APIs are not reachable from every sandbox.)"""
from __future__ import annotations
import json
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

try:
    from ydata_profiling import ProfileReport
    _PROFILING = True
except Exception:  # noqa: BLE001
    _PROFILING = False


def build_client() -> httpx.Client:
    return httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": "h2h-experiment/0.1 (research spike)"},
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
            "smiles": ch.get("smiles"),
            "smiles_valid": smiles_is_valid(ch.get("smiles")),
            "mw": ch.get("mw"),
            "alogp": ch.get("alogp"),
            "n_ic50": ch.get("n_ic50", 0),
            "chembl_moa": ch.get("moa"),
            "n_trials": ct.get("n_trials", 0),
            "max_phase": ct.get("max_phase"),
            "has_terminated": ct.get("has_terminated"),
            "ot_drug_type": ot.get("drug_type"),
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

    render_first_structure(rows)

    if _PROFILING:
        ProfileReport(df.drop(columns=["smiles"]), title="H2H source coverage",
                      minimal=True).to_file(OUT / "data_quality.html")
        print("\n  wrote data_quality.html")
    else:
        print("\n  (ydata-profiling not installed -- skipped HTML report)")

    print(f"\noutputs in: {OUT}")
    client.close()


if __name__ == "__main__":
    main()
