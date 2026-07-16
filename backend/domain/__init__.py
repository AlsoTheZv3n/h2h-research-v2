"""Domain logic: turning source payloads into decision-grade answers.

Not a plugin layer, unlike the adapters. This is typed, cross-entity reasoning
about biochemistry and it stays cohesive.
"""

from __future__ import annotations

from backend.domain.potency import PotencySummary, summarize_ic50

__all__ = ["PotencySummary", "summarize_ic50"]
