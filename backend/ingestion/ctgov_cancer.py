"""ClinicalTrials.gov v2, cancer side: the real registered-trial landscape for a condition.

Distinct from clinicaltrials.py (drug side, keyed by intervention): this queries by CONDITION
TEXT. CT.gov keys diseases by condition string, not MONDO, so the match is SOFT -- a trial whose
primary condition is a different cancer can appear (the gate saw "Colorectal Cancer" trials in an
NSCLC query) -- and the card must say so ("trials mentioning this condition", not "trials of this
cancer"). Every field and behaviour here was verified live against the v2 API in the P1-T4.0 gate
(issue #20).

Two requests per cancer:
  1. the main page -- the TRUE count (`countTotal`) plus one page of studies for the phase/status/
     stopped distributions (a SAMPLE of the count for a big cancer, labelled by n_trials_scanned).
  2. a targeted DACH-recruiting count -- a query-side true count, because a scan over the sampled
     page undercounts it badly (the first 1000 of ~8,400 NSCLC trials held 10 of ~120).
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import httpx

BASE = "https://clinicaltrials.gov/api/v2/studies"

# One page. n_trials is the TRUE countTotal; by_phase/by_status/stopped are distributions over
# this scanned page -- a sample of n_trials for a big cancer -- so n_trials_scanned travels beside
# n_trials and the card labels the distribution as over-a-sample. 1000 is the v2 max pageSize.
_PAGE_SIZE = 1000

_FIELDS = (
    "protocolSection.identificationModule.nctId",
    "protocolSection.statusModule.overallStatus",
    "protocolSection.statusModule.whyStopped",
    "protocolSection.designModule.phases",
)

# A "stopped" trial: started (or was to) and did not run to completion. whyStopped carries a reason
# on most of these (NSCLC: 155/172), never all -- a missing reason is omitted, never invented.
_STOPPED = frozenset({"TERMINATED", "WITHDRAWN", "SUSPENDED"})

# DACH recruiting is a TRUE count via one targeted query (OR-of-countries + RECRUITING filter),
# NOT a scan over the sampled page. The OR de-duplicates a multinational trial (gate: DE 101 +
# AT 38 + CH 40 = 179 raw, OR-query = 122). Verified live.
_DACH_LOCN = "Germany OR Austria OR Switzerland"

# Display orders: known values first in a meaningful order, any unrecognised value appended
# alphabetically so a new CT.gov enum lands visibly at the tail rather than silently dropping.
_PHASE_ORDER = ("EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA")
_STATUS_ORDER = (
    "RECRUITING",
    "NOT_YET_RECRUITING",
    "ENROLLING_BY_INVITATION",
    "ACTIVE_NOT_RECRUITING",
    "COMPLETED",
    "TERMINATED",
    "SUSPENDED",
    "WITHDRAWN",
    "UNKNOWN",
)

_MAX_STOP_REASONS = 8

logger = logging.getLogger(__name__)


def _distribution(counts: Counter[str], order: tuple[str, ...], key: str) -> list[dict[str, Any]]:
    """Counts as [{<key>: value, count: n}], known values in `order`, unknowns appended sorted."""
    known = [k for k in order if counts.get(k)]
    extra = sorted(k for k in counts if k not in order)
    return [{key: k, "count": counts[k]} for k in (*known, *extra)]


async def _count(client: httpx.AsyncClient, params: dict[str, Any]) -> int | None:
    """A countTotal query -> the true total, or None if the response carried none. NEVER 0 for an
    absent total: an absent count is unknown (the clinicaltrials.py rule); a present 0 is real."""
    r = await client.get(BASE, params={"countTotal": "true", "pageSize": 1, **params})
    r.raise_for_status()
    total = r.json().get("totalCount")
    return int(total) if isinstance(total, int) else None


async def _dach_recruiting(client: httpx.AsyncClient, condition: str) -> int | None:
    """TRUE count of RECRUITING trials for this condition with a DE/AT/CH site. A sub-signal: if
    it fails, the caller keeps the rest and marks THIS unknown (None), never 0 recruiting."""
    try:
        return await _count(
            client,
            {
                "query.cond": condition,
                "query.locn": _DACH_LOCN,
                "filter.overallStatus": "RECRUITING",
            },
        )
    except Exception as exc:
        logger.warning("trial-reality DACH sub-query failed for %r: %s", condition, exc)
        return None


async def fetch_trial_reality(client: httpx.AsyncClient, condition: str) -> dict[str, Any] | None:
    """The registered-trial landscape for one cancer condition, or None for a measured ZERO
    trials (a clean EMPTY). Raises on an outage (the caller records source_failed).

    In the returned value, `n_trials` is the TRUE `totalCount`, or None when the API returned a
    page but no count (count unavailable -- NEVER inferred from the page length). `n_trials` is
    never 0 here: a true zero returns None (EMPTY) above, so a null n_trials means only "count
    unavailable", never "no trials". `dach_recruiting` is likewise int (>=0) or None (unknown).
    """
    r = await client.get(
        BASE,
        params={
            "query.cond": condition,
            "countTotal": "true",
            "pageSize": _PAGE_SIZE,
            "fields": ",".join(_FIELDS),
        },
    )
    r.raise_for_status()
    body = r.json()
    total = body.get("totalCount")
    studies = body.get("studies") or []
    if total == 0:
        return None  # measured: no registered trials for this condition -> EMPTY

    phases: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    stop_reasons: Counter[str] = Counter()
    stopped = 0
    for s in studies:
        ps = s.get("protocolSection") or {}
        for ph in (ps.get("designModule") or {}).get("phases") or []:
            phases[ph] += 1
        sm = ps.get("statusModule") or {}
        status = sm.get("overallStatus")
        if status:
            statuses[status] += 1
        if status in _STOPPED:
            stopped += 1
            why = (sm.get("whyStopped") or "").strip()
            if why:
                stop_reasons[why] += 1

    dach = await _dach_recruiting(client, condition)

    return {
        # The text actually queried -- so the card can say "trials mentioning <condition>", owning
        # the soft match rather than implying a curated cohort.
        "condition": condition,
        # TRUE total (countTotal). None only if the API returned a page but no count.
        "n_trials": total if isinstance(total, int) else None,
        # The page we actually read: when < n_trials, the distributions below are a sample.
        "n_trials_scanned": len(studies),
        "by_phase": _distribution(phases, _PHASE_ORDER, "phase"),
        "by_status": _distribution(statuses, _STATUS_ORDER, "status"),
        # count over the scanned page; reasons are the top stated ones (a stopped trial with no
        # whyStopped is counted but contributes no reason -- "—" in the UI, never an invented one).
        "stopped": {
            "count": stopped,
            "reasons": [
                {"reason": reason, "count": n}
                for reason, n in stop_reasons.most_common(_MAX_STOP_REASONS)
            ],
        },
        # TRUE query-side count of DACH-recruiting trials, or None if that sub-query failed.
        "dach_recruiting": dach,
    }
