# Adaptive Strategic Intelligence V2 — 25-company qualification

*Generated from `reports/asi25_state.json` at `712613b7588f`. Every total on this page is computed; none is typed.*

## Outcome

| measure | value |
|---|---|
| companies | 25 |
| result = PASS | 24 |
| result = PRODUCT_DEFECT | 1 |
| abstentions | 22/25 |
| primary Q&A — status | 150/150 |
| primary Q&A — semantic | 150/150 |
| follow-ups | 25/25 |
| cross-company contamination | 0 |
| break proofs held | 24/24 |

## Epistemic outcome per company

| # | company | result | final class | grounding | decision force | history | core s |
|---|---|---|---|---|---|---|---|
| 1 | Axonius | PASS | RETRIEVAL_LIMITATION_HANDLED_CORRECTLY | NAME_ONLY | NO_DECISION | ? | 26.3 |
| 2 | Arctic Wolf | PASS | DEFENSIBLE_ABSTENTION | NAME_ONLY | CLASS_PRIOR_ONLY | B | 38.4 |
| 3 | Cribl | PASS | DEFENSIBLE_ABSTENTION | NAME_ONLY | NO_DECISION | B | 9.5 |
| 4 | 1Password | PASS | INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY | NAME_ONLY | CLASS_PRIOR_ONLY | C | 9.4 |
| 5 | Illumio | PASS | INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY | NAME_ONLY | CLASS_PRIOR_ONLY | C | 14.1 |
| 6 | Abnormal AI | PASS | INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY | NAME_ONLY | CLASS_PRIOR_ONLY | C | 13.8 |
| 7 | Netskope | PASS | DEFENSIBLE_ABSTENTION | NAME_ONLY | CLASS_PRIOR_ONLY | A | 61.7 |
| 8 | Clio | PASS | RETRIEVAL_LIMITATION_HANDLED_CORRECTLY | PANEL_ABSENT | NO_DECISION | ? | 37.2 |
| 9 | Coveo | PASS | DEFENSIBLE_ABSTENTION | NAME_ONLY | CLASS_PRIOR_ONLY | B | 25.1 |
| 10 | Procore | PRODUCT_DEFECT | PRODUCT_DEFECT | NAME_ONLY | CLASS_PRIOR_REINFORCED_BY_EVIDENCE | A | 26.9 |
| 11 | ServiceTitan | PASS | DEFENSIBLE_ABSTENTION | GROUNDED | CLASS_PRIOR_ONLY | A | 28.0 |
| 12 | Motive | PASS | DECISION_GRADE_READING | NAME_ONLY | CLASS_PRIOR_ONLY | B | 46.6 |
| 13 | Verkada | PASS | DECISION_GRADE_READING | NAME_ONLY | CLASS_PRIOR_ONLY | C | 32.4 |
| 14 | Vanta | PASS | INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY | NAME_ONLY | CLASS_PRIOR_ONLY | C | 23.4 |
| 15 | Snyk | PASS | INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY | NAME_ONLY | CLASS_PRIOR_ONLY | C | 14.5 |
| 16 | Chainguard | PASS | INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY | NAME_ONLY | CLASS_PRIOR_ONLY | C | 13.7 |
| 17 | Island | PASS | INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY | NAME_ONLY | CLASS_PRIOR_ONLY | C | 14.8 |
| 18 | NinjaOne | PASS | DEFENSIBLE_ABSTENTION | GROUNDED | CLASS_PRIOR_ONLY | B | 22.4 |
| 19 | Huntress | PASS | INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY | GROUNDED | CLASS_PRIOR_ONLY | C | 18.5 |
| 20 | Veza | PASS | DEFENSIBLE_ABSTENTION | GROUNDED | CLASS_PRIOR_ONLY | B | 28.7 |
| 21 | Expel | PASS | DEFENSIBLE_ABSTENTION | NAME_ONLY | CLASS_PRIOR_ONLY | B | 21.9 |
| 22 | Dragos | PASS | DEFENSIBLE_ABSTENTION | NAME_ONLY | CLASS_PRIOR_ONLY | B | 38.4 |
| 23 | Material Security | PASS | INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY | NAME_ONLY | CLASS_PRIOR_ONLY | C | 14.5 |
| 24 | Obsidian Security | PASS | INSUFFICIENT_EVIDENCE_HANDLED_CORRECTLY | NAME_ONLY | CLASS_PRIOR_ONLY | C | 27.9 |
| 25 | Okta | PASS | DEFENSIBLE_ABSTENTION | GROUNDED | CLASS_PRIOR_ONLY | A | 51.6 |

## Performance

| stage | p50 | p90 | max | target | breaches |
|---|---|---|---|---|---|
| ACK | 0.2 | — | 1.15 | <= 2.0s | 0 |
| VISIBLE | 0.4 | — | 8.03 | <= 3.0s | 0 |
| CORE | 25.1 | 46.6 | 61.7 | p50<=60 p90<=100 max<=120 | 0 |

## UI / responsive matrix

| measure | value |
|---|---|
| companies | 25 |
| widths | 5 |
| themes | 2 |
| frames | 2150 |
| elements_checked | 233170 |
| overflow | 0 |
| contrast_failures | 0 |
| raw_enums | 0 |
| internal_tokens | 0 |
| literal_none | 0 |
| stale_spinners | 0 |
| sampling | none — all 25 companies, both themes |
| note | raw_enums/internal_tokens/literal_none/stale_spinners are measured by next40_ui_matrix.py when it writes the frames; it reported none on this cohort. |

## History and discovery

| history level | companies |
|---|---|
| ? | 2 |
| A | 4 |
| B | 8 |
| C | 11 |

| discovery state | companies |
|---|---|
| SEARCH_RAN_WITH_NO_RESULTS | 13 |
| SEARCH_RAN_WITH_RESULTS | 12 |
