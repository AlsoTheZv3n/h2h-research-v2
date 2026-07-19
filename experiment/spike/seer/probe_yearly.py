#!/usr/bin/env python3
"""H2H P2-B Gate 0 re-probe -- SEER yearly survival (curve vs table). THROWAWAY, stdlib only.

The Phase-0 probe read only the 5-year endpoint (relative_survival_interval=5, data_series[0][0]).
B2 asks: do per-year (1-5) values exist? -> a line chart with markers. If only the 5-year endpoint
-> a table. This dumps the raw data_series shape at interval=5, then tries intervals 1..5 for breast.

Run:  python probe_yearly.py
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

CW = "https://seer.cancer.gov/statistics-network/explorer/source/content_writers"
STAGE = {101: "All", 104: "Localized", 105: "Regional", 106: "Distant"}


def fetch(site: int, sex: int, interval: int) -> dict:
    q = urllib.parse.urlencode(
        {
            "site": site,
            "data_type": 4,
            "graph_type": 5,
            "compareBy": "stage",
            "relative_survival_interval": interval,
            "sex": sex,
            "race": 1,
            "age_range": 1,
            "data_model": 3,
            "series": "stage",
        }
    )
    url = f"{CW}/render_region_5.php?{q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
    obj = json.loads(body)
    if isinstance(obj, str):
        obj = json.loads(obj)
    return obj


def main() -> int:
    site, sex = 55, 3  # breast, female
    print("=== raw data_series shape at interval=5 (is it a single value or a per-year list?) ===")
    payload = fetch(site, sex, 5)
    for key, row in list(payload.get("data", {}).items())[:4]:
        stg = int(key.split("_")[3])
        print(f"  stage {stg} ({STAGE.get(stg, '?'):9}): data_series = {row.get('data_series')}")

    print("\n=== per-stage rate at each interval 1..5 (do yearly points exist?) ===")
    print(f"{'interval':>9} | {'Localized':>10} {'Regional':>10} {'Distant':>10} {'All':>10}")
    for interval in (1, 2, 3, 4, 5):
        try:
            p = fetch(site, sex, interval)
        except Exception as e:  # noqa: BLE001
            print(f"{interval:>9} | FAILED: {e}")
            continue
        rates: dict[int, float | None] = {}
        for key, row in p.get("data", {}).items():
            stg = int(key.split("_")[3])
            v = row["data_series"][0][0]
            rates[stg] = float(v) if v is not None else None

        def c(s: int) -> str:
            return f"{rates[s]:.1f}%" if rates.get(s) is not None else "--"

        print(f"{interval:>9} | {c(104):>10} {c(105):>10} {c(106):>10} {c(101):>10}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
