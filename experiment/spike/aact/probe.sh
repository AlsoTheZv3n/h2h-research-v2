#!/usr/bin/env bash
# Phase 0 spike (KEY: aact) -- ACCESS probe: what in AACT needs a login vs. is open?
# The CT.gov WAF (and AACT's CDN) allowlist the `python-httpx/` User-Agent token;
# bare Mozilla / custom tokens get 403 (see experiment/README.md). Send that token.
set -euo pipefail
UA="python-httpx/0.27 (h2h-experiment/0.1; research spike)"
cd "$(dirname "$0")"; mkdir -p out

echo "== (a) AACT pages: which routes reference an account? =="
curl -s -A "$UA" -o out/aact_home.html     "https://aact.ctti-clinicaltrials.org/"
curl -s -A "$UA" -o out/aact_connect.html  "https://aact.ctti-clinicaltrials.org/connect"
curl -s -A "$UA" -o out/aact_downloads.html "https://aact.ctti-clinicaltrials.org/downloads"
# -> /connect ("Create an Account to Access Cloud Database", /users/sign_in, /users/sign_up)
#    is the LOGIN-GATED path: the live PostgreSQL / cloud DB requires a free account.
# -> /downloads exposes STATIC daily archives with NO account:

echo "== (a2) static daily archives: download withOUT any login/cookie/key =="
# These 302-redirect to a public DigitalOcean Spaces bucket and stream ~2.5 GB each.
# (-o /dev/null here; we proved content once then deleted the 5 GB -- see report.)
curl -sIL -A "$UA" -o /dev/null \
  -w "exported_files daily: HTTP %{http_code} type %{content_type}\n" \
  "https://aact.ctti-clinicaltrials.org/static/exported_files/daily/$(date +%F)?source=web"
curl -sIL -A "$UA" -o /dev/null \
  -w "static_db_copies daily: HTTP %{http_code} type %{content_type}\n" \
  "https://aact.ctti-clinicaltrials.org/static/static_db_copies/daily/$(date +%F)?source=web"
# The exported_files zip (49 pipe-delimited files) INCLUDES outcome_analyses.txt
# (~100 MB) -- the HR table. So AACT's HR data has an open, no-login path via the
# static archive, independent of the login-gated cloud DB.

echo "== (b) DECISIVE cross-check: does CT.gov API v2 expose HAZARD_RATIO openly? =="
# One completed trial with results (FLAURA, osimertinib NSCLC). No login, no key.
curl -s -A "$UA" -o out/ctgov_flaura.json \
  "https://clinicaltrials.gov/api/v2/studies/NCT02296125?fields=resultsSection.outcomeMeasuresModule"
grep -o '"paramType":"Hazard Ratio (HR)"' out/ctgov_flaura.json | wc -l
# -> 4 HR analyses, each with paramValue + ciLowerLimit + ciUpperLimit + pValue.

echo "== per-cancer coverage (5 cancers) is measured by the python probe: =="
echo "   python probe_coverage.py   # writes out/coverage.json + summary table"
