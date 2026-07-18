#!/usr/bin/env bash
# Phase 0 data spike -- CIViC (Clinical Interpretation of Variants in Cancer)
# THROWAWAY. curl + python stdlib only, no deps, no API key, no login.
#
# Endpoint discovery: GET https://civicdb.org/api/graphql -> 404.
# The endpoint is the SAME URL but requires POST with a JSON GraphQL body:
#   POST https://civicdb.org/api/graphql   Content-Type: application/json
# Confirmed open (no key/login): { __typename } -> {"data":{"__typename":"Query"}} HTTP 200.
set -euo pipefail
EP="https://civicdb.org/api/graphql"
q() { curl -s -X POST "$EP" -H "Content-Type: application/json" -d "$1" --max-time 40; }
tc() { python -c "import sys,json;print(json.load(sys.stdin)['data']['evidenceItems']['totalCount'])"; }

echo "### (b) ACCESS -- open, no auth"
q '{"query":"{ __typename }"}'; echo

echo "### Disease resolution (CIViC uses DOID + names, NOT EFO)"
# The 5 target cancers mapped to CIViC disease nodes via diseaseTypeahead/browseDiseases.
# id 8   Lung Non-small Cell Carcinoma  DOID:3908  (<- EFO_0003060 NSCLC)
# id 22  Breast Cancer                  DOID:1612  (<- EFO_0000305; broad node, 300 EIs)
# id 140 Breast Carcinoma               DOID:3459  (narrow node, only 7 EIs -- see report)
# id 556 Pancreatic Cancer              DOID:1793  (<- EFO_0002618; broad node)
# id 169 Pancreatic Carcinoma           DOID:4905  (narrow node, only 5 EIs)
# id 7   Melanoma                       DOID:1909  (<- EFO_0000756)
# id 4   Chronic Myeloid Leukemia       DOID:8552  (<- EFO_0000339)
for term in "Lung Non-small Cell Carcinoma" "Breast" "Pancreatic" "Melanoma" "Myeloid Leukemia"; do
  q "{\"query\":\"{ diseaseTypeahead(queryTerm: \\\"$term\\\") { id name doid } }\"}"; echo
done

echo "### (c) COVERAGE -- PREDICTIVE (biomarker->therapy) evidence items per cancer, with levels"
for pair in "NSCLC:8" "Breast_Cancer:22" "Breast_Carcinoma:140" "Pancreatic_Cancer:556" "Pancreatic_Carcinoma:169" "Melanoma:7" "CML:4"; do
  name=${pair%%:*}; id=${pair##*:}
  pred=$(q "{\"query\":\"{ evidenceItems(diseaseId: $id, evidenceType: PREDICTIVE){ totalCount } }\"}" | tc)
  res=$(q  "{\"query\":\"{ evidenceItems(diseaseId: $id, evidenceType: PREDICTIVE, significance: RESISTANCE){ totalCount } }\"}" | tc)
  echo "$name (id $id): PREDICTIVE=$pred  of which RESISTANCE=$res"
done

echo "### Evidence-level (A-E) distribution -- proof levels are carried (NSCLC PREDICTIVE)"
for lvl in A B C D E; do
  c=$(q "{\"query\":\"{ evidenceItems(diseaseId: 8, evidenceType: PREDICTIVE, evidenceLevel: $lvl){ totalCount } }\"}" | tc)
  echo "  Level $lvl: $c"
done

echo "### Sample populated biomarker->therapy rows (NSCLC)"
q '{"query":"{ evidenceItems(diseaseId: 8, evidenceType: PREDICTIVE, first: 3){ edges{ node{ id evidenceLevel significance therapies{name} molecularProfile{name} disease{name} } } } }"}'; echo

echo "### (d) RESISTANCE MUTATIONS -- retrievable per drug (real examples)"
echo "-- EGFR T790M --"
q '{"query":"{ evidenceItems(molecularProfileName: \"EGFR T790M\", significance: RESISTANCE, first: 2){ totalCount edges{node{id evidenceLevel significance therapies{name} molecularProfile{name} disease{name}}}}}"}'; echo
echo "-- ABL1 T315I (BCR::ABL1, CML) --"
q '{"query":"{ evidenceItems(molecularProfileName: \"T315I\", significance: RESISTANCE, first: 2){ totalCount edges{node{id evidenceLevel significance therapies{name} molecularProfile{name} disease{name}}}}}"}'; echo
echo "-- ALK G1202R --"
q '{"query":"{ evidenceItems(molecularProfileName: \"ALK G1202R\", significance: RESISTANCE, first: 2){ totalCount edges{node{id evidenceLevel significance therapies{name} molecularProfile{name} disease{name}}}}}"}'; echo

echo "### (a) LICENCE -- CC0 (confirmed at docs FAQ)"
curl -s "https://docs.civicdb.org/en/latest/about/faq.html" --max-time 30 \
 | grep -io -m1 "Creative Commons Public Domain Dedication (CC0 1.0 Universal)"
