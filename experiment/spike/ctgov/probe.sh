#!/usr/bin/env bash
# Phase 0 spike (KEY: ctgov) — the real curl commands behind probe.py.
# ClinicalTrials.gov API v2. Open, no key. v2 does NOT need the v1 WAF UA
# workaround: curl's default UA returns 200 (verified below).
set -euo pipefail
BASE="https://clinicaltrials.gov/api/v2/studies"

echo "### WAF / User-Agent check (v1 403s unknown UAs; does v2?)"
for ua in "curl/8" "Mozilla/5.0" "python-httpx/0.27"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "User-Agent: $ua" \
    "$BASE?query.cond=melanoma&countTotal=true&pageSize=1")
  echo "  UA='$ua' -> HTTP $code"
done

echo "### (a) trial count by condition (query.cond, countTotal)"
for c in "non-small cell lung carcinoma" "breast carcinoma" \
         "pancreatic carcinoma" "melanoma" "chronic myeloid leukemia"; do
  enc=$(python -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$c")
  curl -s "$BASE?query.cond=$enc&countTotal=true&pageSize=0" \
    | python -c "import sys,json;print('  %-32s'%'$c', json.load(sys.stdin)['totalCount'])"
done

echo "### (b) whyStopped among TERMINATED|WITHDRAWN (path: statusModule.whyStopped)"
curl -s "$BASE?query.cond=melanoma&filter.overallStatus=TERMINATED%7CWITHDRAWN&countTotal=true&pageSize=2&fields=protocolSection.identificationModule.nctId,protocolSection.statusModule.overallStatus,protocolSection.statusModule.whyStopped" \
  | python -m json.tool

echo "### (c) RECRUITING trials filtered by country (query.locn)"
curl -s "$BASE?query.cond=non-small%20cell%20lung%20carcinoma&filter.overallStatus=RECRUITING&query.locn=Switzerland&countTotal=true&pageSize=0" \
  | python -c "import sys,json;print('  NSCLC recruiting CH:', json.load(sys.stdin)['totalCount'])"

echo "### (d) hazard ratio: completed-with-results, outcome analyses paramType"
curl -s "$BASE?query.cond=melanoma&filter.overallStatus=COMPLETED&aggFilters=results:with&countTotal=true&pageSize=0" \
  | python -c "import sys,json;print('  melanoma completed-with-results:', json.load(sys.stdin)['totalCount'])"
# HR lives at resultsSection.outcomeMeasuresModule.outcomeMeasures[].analyses[]
#   .paramType is FREE TEXT, e.g. "Hazard Ratio (HR)" — NOT an enum "HAZARD_RATIO".
#   Match case-insensitively on "hazard". Also: .paramValue, .ciLowerLimit, .ciUpperLimit
curl -s "$BASE/NCT01245062?fields=resultsSection.outcomeMeasuresModule.outcomeMeasures.analyses" \
  | python -c "import sys,json;d=json.load(sys.stdin);\
oms=d['resultsSection']['outcomeMeasuresModule']['outcomeMeasures'];\
print('  sample HRs:', [(a.get('paramValue'),a.get('ciLowerLimit'),a.get('ciUpperLimit')) for om in oms for a in (om.get('analyses') or []) if 'HAZARD' in (a.get('paramType') or '').upper()][:3])"

# Full measured run: python probe.py  (see probe_output.txt for captured output)
