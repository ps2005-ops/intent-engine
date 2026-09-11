# Adaptive Strategic Intelligence — final ten-company matrix

Frozen SHA: `807a414361b0fbc1999b4595e875c67e2a20524a`  
Service: https://intent-engine-preview-bridge.onrender.com

| Company | Identity | Profile | Lens | Diff | Decision/Abst | Evidence | Chain | CEO | Strategy | Q&A | Follow-up | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Highspot | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PRODUCT_DEFECT** |
| BigID | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PRODUCT_DEFECT** |
| Cyera | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PRODUCT_DEFECT** |
| Monte Carlo Data | PASS | N/A | N/A | N/A | N/A | PASS | N/A | N/A | N/A | PASS | PASS | **RETRIEVAL_FAILED** |
| Veeam | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PRODUCT_DEFECT** |
| Druva | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PRODUCT_DEFECT** |
| Slalom | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PRODUCT_DEFECT** |
| Sigma Computing | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PRODUCT_DEFECT** |
| ZoomInfo | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **PRODUCT_DEFECT** |
| Point B | PASS | **FAIL** | **FAIL** | **FAIL** | **FAIL** | PASS | **FAIL** | PASS | PASS | PASS | PASS | **PRODUCT_DEFECT** |

### Per company

| Company | P/L/D | model | source | lens | state | chain | spec | quotes | leaks | Q&A | CORE |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Highspot | `YYN` | SUBSCRIPTION_SOFTWARE | SUBJECT_EVIDENCE | revenue_gtm | POTENTIAL_DOMAINS | INVESTIGATION_CHAIN | 0.235 | 5 | 0 | 6/6 | 18.1s |
| BigID | `YYN` | SUBSCRIPTION_SOFTWARE | SUBJECT_EVIDENCE | data_security_governance | POTENTIAL_DOMAINS | INVESTIGATION_CHAIN | 0.235 | 5 | 0 | 6/6 | 15.0s |
| Cyera | `YYN` | SUBSCRIPTION_SOFTWARE | SUBJECT_EVIDENCE | data_security_governance | POTENTIAL_DOMAINS | INVESTIGATION_CHAIN | 0.176 | 3 | 0 | 6/6 | 18.6s |
| Monte Carlo Data | `NNN` | UNKNOWN | NONE | — | NOTHING | NO_CHAIN | 0.059 | 0 | 0 | 6/6 | 6.3s |
| Veeam | `YYN` | SUBSCRIPTION_SOFTWARE | SUBJECT_EVIDENCE | enterprise_data_ai | POTENTIAL_DOMAINS | INVESTIGATION_CHAIN | 0.294 | 5 | 0 | 6/6 | 29.0s |
| Druva | `YYN` | SUBSCRIPTION_SOFTWARE | SUBJECT_EVIDENCE | enterprise_data_ai | POTENTIAL_DOMAINS | INVESTIGATION_CHAIN | 0.118 | 3 | 0 | 6/6 | 26.0s |
| Slalom | `YYN` | PEOPLE_OR_ROUTE_BASED_SERVICES | SUBJECT_EVIDENCE | consulting_portfolio | POTENTIAL_DOMAINS | INVESTIGATION_CHAIN | 0.176 | 4 | 0 | 6/6 | 36.6s |
| Sigma Computing | `YYN` | SUBSCRIPTION_SOFTWARE | SUBJECT_EVIDENCE | data_infrastructure | POTENTIAL_DOMAINS | INVESTIGATION_CHAIN | 0.294 | 5 | 0 | 6/6 | 24.4s |
| ZoomInfo | `YYN` | SUBSCRIPTION_SOFTWARE | SEC_SIC | revenue_gtm | POTENTIAL_DOMAINS | INVESTIGATION_CHAIN | 0.353 | 5 (1 broken) | 0 | 6/6 | 49.3s |
| Point B | `NNN` | UNKNOWN | NONE | — | NOTHING | NO_CHAIN | 0.059 | 0 | 0 | 6/6 | 44.9s |

### Numeric verdict

```
IDENTITY:                           10/10
PROFILE:                            8/10   (1 FAIL)
PROFILE_AVAILABLE:                  8/10   (1 FAIL)
LENS_AVAILABLE:                     8/10   (1 FAIL)
DECISION_READING_AVAILABLE:         8/10   (8 defensible abstention)   (1 FAIL)
STRATEGIC_LENS:                     8/10   (1 FAIL)
WHY_THIS_COMPANY:                   8/10   (1 FAIL)
DECISION_OR_DEFENSIBLE_ABSTENTION:  8/10   (1 FAIL)
CAUSAL_OR_INVESTIGATION:            8/10   (1 FAIL)
EVIDENCE:                           10/10
COUNTEREVIDENCE_OR_LIMITATION:      9/10
DECISION_VALUE:                     9/10
CEO_ROLE:                           9/10
STRATEGY_ROLE:                      9/10
QA:                                 10/10
FOLLOWUP_CONTEXT:                   10/10
NO_PRODUCT_DEFECT:                  1/10   (9 FAIL)
QA_ANSWERS:                         60/60
FOLLOWUP:                           10/10

RAW_ENUM/INTERNAL_TERM_LEAKS:       0
ATTRIBUTION/SPAN_DEFECTS:           1
UNEXPLAINED_TEMPLATE_COLLAPSES:     2
PAIRS FLAGGED FOR INSPECTION:       13
ENDLESS_SPINNERS:                   0
```

### Performance

| metric | value |
|---|---|
| CORE p50 | 25.2s |
| CORE p90 | 44.9s |
| CORE max | 49.3s |
