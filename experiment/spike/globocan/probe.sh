#!/usr/bin/env bash
# GLOBOCAN / IARC Global Cancer Observatory -- Phase 0 data spike (KEY: globocan)
# The real curl commands run against the open JSON gateway. No login, no API key.
set -euo pipefail

BASE="https://gco.iarc.who.int/gateway_prod/api/globocan/v3/2024"
QS="?group_CRC=1&include_nmsc=1&include_nmsc_other=1"
OUT="$(dirname "$0")/out"; mkdir -p "$OUT"

# 0. The site is a Vue SPA. The API base was recovered from its JS bundle:
#    VITE_APP_API = https://gco.iarc.who.int/gateway_prod/api/globocan/v3/[vdb]/
#    [vdb] = data_version = 2024  (GLOBOCAN 2022 estimates).
curl -sSL "https://gco.iarc.who.int/today/en/dataviz/tables" -o "$OUT/tables.html"
curl -sSL "https://gco.iarc.who.int/today/assets/main-ntK6H0m7.js" -o "$OUT/main.js"
grep -oE 'VITE_APP_API:`[^`]+`' "$OUT/main.js" | head -1

# 1. Metadata: cancer site codes + country codes (no auth).
curl -sSL "$BASE/meta/cancers/all/"     -o "$OUT/cancers.json"
curl -sSL "$BASE/meta/populations/all/" -o "$OUT/populations.json"

# 2. ASR incidence+mortality, all cancers, per country (900=World 840=USA 826=UK 392=Japan).
for pop in 900 840 826 392; do
  curl -sSL "$BASE/data/rate/0_1_2/0_1_2/$pop/all/$QS" -o "$OUT/rate_$pop.json"
done

# 3. Terms of use / copyright (SPA shell; real text lives in main.js -> grep it).
curl -sSL "https://gco.iarc.who.int/en/data-and-methods/terms-of-use" -o "$OUT/terms.html"
grep -oiE 'Materials \(graphs, tables\) may be used.{0,220}' "$OUT/main.js" | head -1

echo "done -- inspect $OUT/rate_900.json (field: asr). Then: python probe.py"
