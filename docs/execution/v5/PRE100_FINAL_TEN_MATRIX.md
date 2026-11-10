| Company | AC ms | Canonical identity | Business model | Elig | Chosen pattern | Ack s | CORE s | QA-ready s | Docs | Roles | Prov | Q&A | Timer | Leak | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Synopsys | 204 | Synopsys Inc | SUBSCRIPTION_SOFTWARE | 11 | -- | 0.81 | 58.3 | 88.4 | 15 | ['direction', 'identity_or_product', 'market'] | yes | 6/6 | yes | 0 | FULL_REPORT |
| Emerson Electric | 181 | Emerson Electric Co | -- | -- | -- | 0.79 | 25.3 | 37.6 | 3 | ['direction'] | yes | 6/6 | yes | 0 | FULL_REPORT |
| Lowe's Companies | 214 | Lowes Companies Inc | SCALE_RETAIL | 7 | -- | 0.81 | 68.7 | 97.6 | 5 | ['direction', 'identity_or_product', 'market'] | yes | 6/6 | yes | 0 | FULL_REPORT |
| BlackRock | 223 | BlackRock, Inc. | BALANCE_SHEET_OR_NETWORK | 11 | -- | 0.67 | 55.6 | 77.8 | 6 | ['direction', 'identity_or_product', 'market'] | yes | 6/6 | yes | 0 | FULL_REPORT |
| Amgen | 231 | Amgen Inc | REGULATED_PRODUCT_OR_PROVIDER | 9 | -- | 0.65 | 55.3 | 73.6 | 13 | ['direction', 'identity_or_product', 'market'] | yes | 6/6 | yes | 0 | FULL_REPORT |
| SLB | 185 | Slb Limited | COMMODITY_PRODUCER | 5 | capacity_ahead_of_demand | 0.86 | 55.8 | 65.2 | 7 | ['direction', 'identity_or_product', 'market'] | no | 6/6 | yes | 0 | FULL_REPORT |
| T-Mobile US | 307 | T-Mobile US, Inc. | CONTRACTED_OR_RATE_BASE_ASSETS | 5 | capacity_ahead_of_demand | 1.45 | 94.3 | 121.8 | 5 | ['direction', 'identity_or_product'] | yes | 6/6 | yes | 0 | FULL_REPORT |
| Old Dominion Freight Line | 193 | Old Dominion Freight Line, Inc. | PEOPLE_OR_ROUTE_BASED_SERVICES | 11 | -- | 0.72 | 84.0 | 119.8 | 12 | ['direction', 'identity_or_product', 'market'] | yes | 6/6 | yes | 0 | FULL_REPORT |
| Novartis | 316 | Novartis AG | REGULATED_PRODUCT_OR_PROVIDER | 9 | -- | 1.59 | 72.7 | 89.9 | 6 | ['direction', 'identity_or_product', 'market'] | yes | 6/6 | yes | 0 | FULL_REPORT |
| Sprouts Farmers Market | 193 | Sprouts Farmers Market, Inc. | SCALE_RETAIL | 7 | -- | 1.99 | 94.3 | 120.8 | 9 | ['direction', 'identity_or_product', 'market'] | yes | 6/6 | yes | 0 | FULL_REPORT |

### Thesis audit
- thesis skeletons (subject removed): 2 across 9 readings
- of which ASSERTED a reading: 1 skeleton(s) over 2 companies; the rest asserted none
- duplicated thesis groups: 2
  - **Synopsys, Lowe's Companies, BlackRock, Amgen, Old Dominion Freight Line, Novartis, Sprouts Farmers Market** — models ['BALANCE_SHEET_OR_NETWORK', 'PEOPLE_OR_ROUTE_BASED_SERVICES', 'REGULATED_PRODUCT_OR_PROVIDER', 'SCALE_RETAIL', 'SUBSCRIPTION_SOFTWARE'], patterns ['']
    > No curated transition pattern matched <SUBJECT> in this pass, so the reading below is not built from one.
    KIND: ABSTENTION — no reading was asserted for any of these, so there is no duplicated thesis to explain.
  - **SLB, T-Mobile US** — models ['COMMODITY_PRODUCER', 'CONTRACTED_OR_RATE_BASE_ASSETS'], patterns ['capacity_ahead_of_demand']
    > <SUBJECT> appears to be committing capital to capacity ahead of uncertain demand. The evidence supports this as a low-confidence hypothesis, not a settled fact.
    KIND: SHARED PATTERN ['capacity_ahead_of_demand'] across 2 companies in 2 model class(es).
    JUDGE: do these businesses share the mechanism the reading rests on? Same thesis is permitted where they do.
- company-specific mechanism present: 2/10 (20%)
- classification reached the gate: 9/10; UNKNOWN: ['Emerson Electric']

### Aggregates
- autocomplete: median=204ms p90=307ms (n=10)
- CORE: p50=58.3s p90=94.3s max=94.3s <=120s 100% (n=10)
- strategic Q&A ready: p50=88.4s p90=120.8s (n=10)
- evidence: median documents=6.5; all-three-roles 80%; provenance 90%
- Q&A: 60/60 substantive-and-owned (100%)
- counterevidence: PRESENT=10
- terminal: 10/10
- identity bound: 10/10
- foreign company on a report: 0
- spinner after terminal: 0
- internal vocabulary leaks: 0
- rows with defects: 0/10

### Autocomplete prefix proof
- `lowe` -> Lowes Companies Inc (183ms, score 0.5, OK)
- `lowe's` -> Lowes Companies Inc (339ms, score 0.5, OK)
- `Lowe's Companies` -> Lowes Companies Inc (187ms, score 0.5, OK)
- `old d` -> Old Dominion Freight Line, Inc. (195ms, score 1.0, OK)
- `old dominion` -> Old Dominion Freight Line, Inc. (189ms, score 1.0, OK)
- `t-mob` -> T-Mobile US, Inc. (212ms, score 1.0, OK)
- `t-mobile` -> T-Mobile US, Inc. (186ms, score 1.0, OK)
- `slb` -> Slb Limited (246ms, score 1.0, OK)
- median=195ms p90=246ms
