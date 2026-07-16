"""SQLAlchemy models. Import every module here so Alembic autogenerate sees them."""

from __future__ import annotations

from backend.models.base import Base

__all__ = ["Base"]
