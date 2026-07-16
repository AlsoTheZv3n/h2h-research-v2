"""Seed drugs to probe. Mostly KRAS G12C for a dense, resolvable entity space,
plus one different target and one ADC to see where the small-molecule model breaks."""

SEED_DRUGS: list[str] = [
    "sotorasib",               # KRAS G12C, small molecule, approved
    "adagrasib",               # KRAS G12C, small molecule, approved
    "divarasib",               # KRAS G12C, small molecule, phase 3
    "osimertinib",             # EGFR, small molecule, approved (different target)
    "trastuzumab deruxtecan",  # HER2, ADC/biologic -- expected to lack a simple SMILES
]
