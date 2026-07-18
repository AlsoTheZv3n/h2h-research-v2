"""SQLAlchemy models. Import every module here so Alembic autogenerate sees them."""

from __future__ import annotations

from backend.models.abstract import Abstract, DrugAbstract
from backend.models.base import Base
from backend.models.cancer import Cancer
from backend.models.cancer_fact import CancerFactRow
from backend.models.drug import DataMaturity, Drug
from backend.models.fact import FactRow

__all__ = [
    "Abstract",
    "Base",
    "Cancer",
    "CancerFactRow",
    "DataMaturity",
    "Drug",
    "DrugAbstract",
    "FactRow",
]
