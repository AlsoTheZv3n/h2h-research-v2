#!/usr/bin/env bash
# H2H Phase 0 spike -- SEER (KEY: seer). THROWAWAY probe. Real calls only.
#
# Question: can we retrieve STAGE-WISE (localized/regional/distant) 5-year
# RELATIVE survival per cancer from an OPEN SEER source WITHOUT an account?
#
# Finding: YES. SEER*Explorer is a public web app whose data comes from
# undocumented-but-open PHP JSON endpoints under
#   https://seer.cancer.gov/statistics-network/explorer/source/content_writers/
# No login, no API key, no data-use agreement. (The SEER *research microdata*
# API at api.seer.cancer.gov DOES require a login -- we do NOT use it.)
#
# Run:  bash probe.sh
set -euo pipefail

EXP="https://seer.cancer.gov/statistics-network/explorer"
CW="$EXP/source/content_writers"

echo "############################################################"
echo "# 0. ACCESS -- is the research-microdata API gated? (yes)   "
echo "############################################################"
# api.seer.cancer.gov = the SEER*API for case-level microdata. Home page shows a
# Login link; microdata needs a signed DUA. We do NOT use this. Shown for the record.
curl -s "https://api.seer.cancer.gov/" -m 20 | grep -oiE '/login|SEER API' | sort -u || true
echo

echo "############################################################"
echo "# 1. The data dictionary (open, no auth): site & stage codes"
echo "############################################################"
# get_var_formats.php returns the full code<->label maps used by the app.
curl -s "$CW/get_var_formats.php" -m 25 -o var_formats.json
echo "saved var_formats.json ($(wc -c < var_formats.json) bytes)"
# Codes we care about (verified against the source itself):
#   data_type: 4 = Survival
#   graph_type: 5 = 5-Year Survival
#   relative_survival_interval: 5 = 5-year Relative Survival
#   stage: 101 All, 104 Localized, 105 Regional, 106 Distant, 107 Unstaged
#   sex: 1 Both, 2 Male, 3 Female
#   SITE codes -> our 5 cancers:
#     NSCLC   -> NO native "NSCLC" site. Closest: 47 = Lung and Bronchus
#               (includes small cell). NSCLC histologies exist separately:
#               612 Adenocarcinoma, 610 Squamous, 613 Large cell of lung.
#     Breast  -> 55 (report Female, sex=3, for the representative cohort)
#     Pancreas-> 40
#     Melanoma-> 53 (Melanoma of the Skin)
#     CML     -> 97 (Chronic Myeloid Leukemia)
echo

echo "############################################################"
echo "# 2. COVERAGE -- stage-wise 5-yr relative survival per cancer"
echo "############################################################"
# render_region_5.php is the actual data call the chart makes.
# compareBy=stage makes the x-axis the stage; each data row is one stage.
survival() {
  local label="$1" site="$2" sex="$3"
  echo "----- $label (site=$site, sex=$sex) -----"
  curl -s "$CW/render_region_5.php?site=$site&data_type=4&graph_type=5&compareBy=stage&relative_survival_interval=5&sex=$sex&race=1&age_range=1&data_model=3&series=stage" \
    -m 30 -w '\n[HTTP %{http_code}]\n'
  echo
}
survival "NSCLC proxy: Lung and Bronchus" 47 1
survival "NSCLC histology: Adenocarcinoma of lung" 612 1
survival "Breast (Female)"                 55 3
survival "Pancreas"                        40 1
survival "Melanoma of the Skin"            53 1
survival "CML"                             97 1   # returns ONLY All-Stages -> stage block EMPTY

echo "Done. Data rows keyed sex_race_age_stage_subtype_site;"
echo "data_series = [rate, rate_se, lower_ci, upper_ci, count]."
