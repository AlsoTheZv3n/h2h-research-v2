"""SQLAlchemy models. Import every module here so Alembic autogenerate sees them."""

from __future__ import annotations

from backend.models.abstract import Abstract, DrugAbstract
from backend.models.base import Base
from backend.models.cancer import Cancer
from backend.models.cancer_fact import CancerFactRow
from backend.models.cbioportal_study_map import CBioPortalStudyMap
from backend.models.change_event import ChangeEvent
from backend.models.disease_source_map import DiseaseSourceMap
from backend.models.drug import DataMaturity, Drug
from backend.models.drug_target import DrugTarget
from backend.models.fact import FactRow
from backend.models.target import Target
from backend.models.target_fact import TargetFactRow

__all__ = [
    "Abstract",
    "Base",
    "CBioPortalStudyMap",
    "Cancer",
    "CancerFactRow",
    "ChangeEvent",
    "DataMaturity",
    "DiseaseSourceMap",
    "Drug",
    "DrugAbstract",
    "DrugTarget",
    "FactRow",
    "Target",
    "TargetFactRow",
]
