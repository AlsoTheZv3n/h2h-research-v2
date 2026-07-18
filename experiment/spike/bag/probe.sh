#!/usr/bin/env bash
# Phase 0 data spike -- BAG Spezialitätenliste (Swiss reimbursed-drug list + prices).
# THROWAWAY. Real calls only. No auth, no key. curl + stdlib only.
#
# Discovery trail (how the endpoint was found), then the coverage measurement.
set -euo pipefail

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
API="https://epl.bag.admin.ch/api/sl/"          # <- the SL backend, discovered from the SPA bundle
OUT="$(dirname "$0")/out"
mkdir -p "$OUT"

# ---------------------------------------------------------------------------
# 0. ACCESS DISCOVERY
# ---------------------------------------------------------------------------
# opendata.swiss does NOT carry the SL (searched -> 0 hits). The SL webapp at
# www.spezialitaetenliste.ch 302-redirects to https://sl.bag.admin.ch/sl, an
# Angular SPA. The API base lives in the JS bundle:
#   grep -o 'epl.bag.admin.ch/api/sl/' chunk-*.js
# Reproduce the "not on opendata.swiss" finding:
curl -sSL -m 40 -A "$UA" \
  "https://ckan.opendata.swiss/api/3/action/package_search?q=Spezialit%C3%A4tenliste&rows=20" \
  -o "$OUT/opendata_search.json"   # -> result.count == 0

# The two public, unauthenticated SL endpoints used by the official webapp:
#   GET public/medicinal-products/filters              (ATC/IT-code/substance facets)
#   GET public/medicinal-products?search=&page=&size=  (products incl. prices)
#   GET packages/{pcid}/prices/all                     (price history; not needed for a spot price)
curl -sSL -m 60 -A "$UA" "${API}public/medicinal-products/filters" -o "$OUT/filters.json"

# ---------------------------------------------------------------------------
# 1. COVERAGE -- one on-label drug per cancer, real list price per pack
# ---------------------------------------------------------------------------
# search term  | cancer            | on-label agent
#   Tagrisso    NSCLC               osimertinib
#   Herceptin   breast carcinoma    trastuzumab
#   Tafinlar    melanoma            dabrafenib
#   Glivec      CML                 imatinib
#   Abraxane    pancreatic carcinoma nab-paclitaxel (+ gemcitabine)
for q in Tagrisso Herceptin Tafinlar Glivec Abraxane; do
  curl -sSL -m 60 -A "$UA" -H "Accept: application/json" \
    "${API}public/medicinal-products?page=1&size=20&search=${q}" \
    -o "$OUT/search_${q}.json"
done

echo "Fetched. Now parse with probe.py to print the coverage table."
