# Spike report -- BAG Spezialitätenliste (KEY: `bag`)

Swiss Federal Office of Public Health (BAG/FOPH) reimbursed-drug list ("Spezialitätenliste",
SL) with official list prices. Phase 0 throwaway spike. All numbers from **real calls made
2026-07-18**; en-US formatting.

## Verdict: GREEN

A public, unauthenticated JSON API returns, for all 5 test cancers, an on-label oncology
drug with a real Swiss list price per pack (both ex-factory and public/retail, in CHF).
Coverage **5/5**. The one caveat is licence clarity, not access (see below).

---

## (a) Access

| Question | Finding |
|---|---|
| Login required? | **No.** Plain GET, no cookie/token. |
| API key required? | **No.** |
| On opendata.swiss? | **No** -- `package_search?q=Spezialitätenliste` returns `count: 0`. The SL is **not** an OGD dataset. |
| Where the data actually lives | The official webapp `www.spezialitaetenliste.ch` 302-redirects to the Angular SPA `https://sl.bag.admin.ch/sl`. Its JS bundle calls the backend **`https://epl.bag.admin.ch/api/sl/`**. |
| Machine-readable? | **Yes, JSON.** No XML/CSV bulk download was found on opendata.swiss; the JSON API is the live source. |
| Gotcha | The `*.admin.ch` edge WAF **403s a bare/default User-Agent** (same block hit on `www.admin.ch` terms page). A normal browser UA string passes. Build with a real UA header. |

### Endpoints used (all public, no auth)

- `GET public/medicinal-products?search={term}&page={n}&size={n}` -- products **incl. prices** inline.
- `GET public/medicinal-products/filters` -- ATC / IT-code / substance / holder facets (816 KB).
- `GET packages/{pcid}/prices/all` -- price history (not needed for a spot price).

### Schema (measured, per priced pack)

`items[].medicinalProducts[].packagedMedicinalProducts[]` carries:
`pcid`, `gtin`, `packSize` (e.g. `"30 Stk"`), **`exFactoryPrice`** (Fabrikabgabepreis),
**`retailPrice`** (Publikumspreis), `validFrom/validTo`, `lastPriceChange`, `listType` ("SL").
The parent `medicinalProduct` carries `itCode` (IT class, e.g. `07.16.10. Cytostatica`),
`ingredients` (substance + strength), and rich `limitations[]` with the reimbursed
**indication text** -- enough to confirm each drug is on-label for its cancer.

---

## (b) Coverage -- Swiss list price per cancer

COVERAGE = per cancer, is at least one on-label drug's Swiss list price retrievable openly.
Prices are the currently-valid SL entry for the smallest listed pack shown.

| Cancer | On-label drug (searched) | Pack | Ex-factory CHF | Public/retail CHF | On-label confirmed (SL limitation) | State |
|---|---|---|---|---|---|---|
| NSCLC | Tagrisso / osimertinib, Tabl 40 mg | 30 Stk | 5,012.50 | 5,450.65 | "1L NSCLC ... EGFR Exon 19/21" | **POPULATED** |
| Breast carcinoma | Herceptin / trastuzumab, Trockensub 150 mg | 1 Amp | 502.52 | 560.10 | "adjuvante Therapie des Mammakarzinoms" | **POPULATED** |
| Melanoma | Tafinlar / dabrafenib, Kaps 50 mg | 28 Stk | 820.18 | 908.40 | "Melanom ... BRAF-V600-Mutation" | **POPULATED** |
| CML | Glivec / imatinib, Filmtabl 100 mg | 60 Stk | 808.40 | 874.30 | "Ph+ chronisch-myeloischer Leukämie" | **POPULATED** |
| Pancreatic carcinoma | Abraxane / nab-paclitaxel, Trockensub 100 mg | 1 Durchstf | 296.98 | 332.10 | "Adenokarzinom des Pankreas ... + Gemcitabin" | **POPULATED** |

**5 / 5 POPULATED.** Every cancer returns a real on-label drug with a real CHF list price.
Other on-label agents are also present (generic `gemcitabin`: 4 hits; multiple Cytostatica
under IT `07.16.10.`), so this is not a hand-picked single-drug win.

### ID verification note
The five EFO IDs in the task are Open Targets identifiers; the SL does **not** use EFO/ontology
codes. The source-native verification done here is stronger for this dataset: each drug's SL
**limitation/indication text** was read and confirmed to name the target cancer (quoted above).
The SL groups oncology under IT-code `07.16. Oncologica` (`07.16.10. Cytostatica`,
`.20. Hormone`, `.30. Radio-Isotope`, `.40. Andere`).

---

## (c) Derived cost-per-cycle -- feasibility (no number fabricated)

**Feasible, but only as a clearly-labelled approximation with an external, stated assumption.**

- The SL gives **price-per-pack + packSize + strength** (e.g. Tagrisso 40 mg x 30). It does
  **not** carry a dose or dosing schedule.
- A per-cycle cost therefore requires an **external dosing assumption** (SmPC/label): e.g.
  osimertinib 80 mg once daily -> 56 tablets per 28-day cycle -> ~1.87 packs of 40 mg.
  That assumption must be **shown, not hidden**.
- Weight/BSA-dosed agents (Herceptin mg/kg, Abraxane mg/m^2) additionally need a **body-size
  assumption** (e.g. 1.7 m^2 / 70 kg), which is another stated input.
- **No number is computed here** -- only feasibility is asserted. Any figure the app derives
  MUST be labelled a **"Swiss SL list-price approximation"**, never "the cost of treatment":
  it is ex-factory/public list price, excludes hospital/tender discounts, the confidential
  price-model rebates the SL itself flags (`priceModel: true`, e.g. AstraZeneca rebate noted
  in the Tagrisso limitation), VAT nuances, and wastage.

---

## Licence / terms

- **Access is open** (no auth, no key). **Licence is not explicitly declared** on the API or
  a dataset page -- because the SL is *not* published as an opendata.swiss dataset with an OGD
  licence tag. It is official federal regulatory content served by the SL webapp backend.
- General Swiss Confederation terms (`admin.ch`): reproduction of texts/data is generally
  permitted **with source citation**; commercial reuse can carry conditions. That page is
  itself WAF-gated, so the exact clause could not be fetched in-spike -- **treat licence as
  "attribution, terms to confirm"**, not a clean CC0/OGD grant.
- Redistribution stance for the app: **attribution + explicit source/date label**, and the
  "list-price approximation" framing from (c). Prices are time-stamped (`validFrom`,
  `lastPriceChange`) so provenance is easy to cite.

## Rationale

Open, no-auth, machine-readable JSON; a stable price schema; and a real on-label CHF price for
5/5 cancers -- with source-native indication text proving each match. That is a genuinely
populated evidence block, not an availability mirage. Downgrades from an unqualified green: (1)
licence is attribution-with-terms-to-confirm rather than a clean OGD grant, and (2) the value
is a **list price**, so the UI must label it as an approximation and never conflate it with
real treatment cost. Neither blocks a build.

## Gotchas for the next builder

1. **Undocumented API.** `epl.bag.admin.ch/api/sl/` is the SPA backend, not a published API;
   it can change without notice. Cache responses; pin/monitor the schema.
2. **WAF needs a browser User-Agent** on `*.admin.ch`; default UAs get 403.
3. **`search` is the reliable retrieval path.** The `itCodes` / `atcCodes` query params were
   sent but **not honored server-side** (results still contained unrelated ATC classes;
   `total` stayed at the full catalog 3,393) -- filtering appears to be client-side. Don't rely
   on server-side facet filtering; filter the returned items yourself, or drive by `search`.
4. **Prices are inline** in the product search response -- no second call needed for a spot
   price. `packages/{pcid}/prices/all` is only for history.
5. Two prices per pack: **`exFactoryPrice`** (ex-factory) vs **`retailPrice`** (public). Pick
   deliberately and label which one; they differ by the distribution margin.

## Files
- `probe.sh` -- the real curl commands (discovery + coverage).
- `probe.py` -- stdlib-only reproducer; prints the coverage table above. Run: `uv run python spike/bag/probe.py` from `experiment/`.
- `out/` -- captured JSON (`search_*.json`, `filters.json`, `opendata_search.json`).
