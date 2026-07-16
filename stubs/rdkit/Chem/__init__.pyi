"""Minimal stubs for the RDKit surface we use.

rdkit ships its own stubs, and they do not parse: Chem/rdmolfiles.pyi declares
`GetText(mol, confId=-1, props_list: ..., structstd: ..., classstd: ... = ...,
structstd: ..., classstd: ...)` -- a non-default parameter after a default one, and
two parameters declared twice. mypy fails the entire run on that, so a defect in
someone else's package would cost us type checking on ours.

These shadow them via mypy_path. Narrow on purpose: they describe what
backend/domain/structure.py actually calls, and nothing else.
"""

from typing import Any

class Mol: ...

def MolFromSmiles(smiles: str) -> Mol | None: ...
def MolToSmiles(mol: Mol, **kwargs: Any) -> str: ...
