#!/usr/bin/env python3
"""S4 -- Sponsor: how expensive is the name problem? THROWAWAY.

Pull lead sponsors for a large oncology trial sample. Count DISTINCT raw strings; print the
top ~60 by trial count so a human can estimate distinct real entities. The ratio
raw-strings : real-entities is the cost estimate for a normalisation layer.

Run:  uv run python s4_sponsors.py
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections import Counter

CT = "https://clinicaltrials.gov/api/v2/studies"
UA = "python-httpx/0.27 (h2h-spike-backlog; research)"


def page(cond: str, token: str | None) -> dict:
    p = {
        "query.cond": cond,
        "pageSize": 1000,
        "fields": "protocolSection.sponsorCollaboratorsModule.leadSponsor.name",
    }
    if token:
        p["pageToken"] = token
    req = urllib.request.Request(CT + "?" + urllib.parse.urlencode(p), headers={"User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=90))


def collect(cond: str, want: int) -> list[str]:
    names: list[str] = []
    token = None
    while len(names) < want:
        d = page(cond, token)
        for st in d.get("studies", []):
            lead = (
                st.get("protocolSection", {})
                .get("sponsorCollaboratorsModule", {})
                .get("leadSponsor", {})
                .get("name")
            )
            if lead:
                names.append(lead)
        token = d.get("nextPageToken")
        if not token:
            break
    return names


def main() -> None:
    # "cancer" is broad; CT.gov maps it to the neoplasm MeSH branch.
    names = collect("cancer", 12000)
    c = Counter(names)
    print(f"oncology trials sampled: {len(names)}")
    print(f"DISTINCT raw lead-sponsor strings: {len(c)}")
    print("\n=== top 60 lead sponsors by trial count (inspect for collapsible variants) ===")
    for name, n in c.most_common(60):
        print(f"  {n:5}  {name}")


if __name__ == "__main__":
    main()
