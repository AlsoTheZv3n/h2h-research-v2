"""Render a molecule to SVG.

Server-side, with the same RDKit the spike used, for two reasons: it is the only
thing that can tell a valid SMILES from a plausible-looking string, and one
canonical renderer beats a second chemistry stack in the browser.
"""

from __future__ import annotations

from functools import lru_cache

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D


@lru_cache(maxsize=512)
def render_svg(smiles: str, width: int = 380, height: int = 300) -> str | None:
    """SMILES -> SVG, or None when RDKit cannot parse it.

    None means "this string is not a molecule we can draw" -- a biologic, or a
    structure ChEMBL does not carry. The caller turns that into an honest 404, never
    a blank image.

    Cached: the same handful of drugs get looked at repeatedly, and the parse is the
    expensive half.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    options = drawer.drawOptions()
    # Match the page: thin lines, no heavy black, transparent behind the molecule.
    options.clearBackground = False
    options.bondLineWidth = 1.4
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return str(drawer.GetDrawingText())
