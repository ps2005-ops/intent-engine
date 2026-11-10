# Differentiation — 25 companies, measured

*Generated from `reports/asi25_state.json` at `712613b7588f`. Every total on this page is computed; none is typed.*

## The headline correction

The previous close reported *distinct questions 4 → 8* and *largest
identical group 22-of-33 → 7-of-14*. Those figures came from
`reports/asi25_differentiation.json`, which was a **17-company**
file written mid-run and never overwritten, because the
orchestrator's collection step copied a fresh result only when no
file was already in the way. Measured over all 25:

| measure | forty | twenty-five |
|---|---|---|
| companies | 40 | 25 |
| carrying a decision question | 33 | 22 |
| DISTINCT_QUESTIONS | 4 | 7 |
| LARGEST_IDENTICAL_QUESTION_GROUP | 22 | 16 |
| share of questioned companies in that one group | 66.7% | 72.7% |
| EVIDENCE_LED | 3 | 0 |
| CLASS_PRIOR_ONLY | 29 | 21 |
| NO_DECISION | 7 | 3 |
| grounding verdict | ABSENT — the field did not exist | {"NAME_ONLY": 19, "PANEL_ABSENT": 1, "GROUNDED": 5} |

Template collapse on the decision question is **worse** on this
cohort as a share of the companies that reached a question, not
better. Reported that way because it is what the state file says.

## Every decision question in the cohort

| companies | question |
|---|---|
| 16 | `what to charge, and for what, without losing more customer count than the price gains?` |
| 1 | `what to charge, and for what, without losing more customer count among larger customers than the price gains?` |
| 1 | `what to charge, and for what, without losing more device count than the price gains?` |
| 1 | `what to charge, and for what, without losing more tenant count than the price gains?` |
| 1 | `what to charge, and for what, without losing more customer count among organizations to control access than the price gains?` |
| 1 | `what to charge, and for what, without losing more billable headcount or capacity than the price gains?` |
| 1 | `what to charge, and for what, without losing more customer count among human users than the price gains?` |

## Rates

| measure | value |
|---|---|
| COMPANY_SPECIFIC_MECHANISM_RATE | 24.0% |
| GENERICITY_FAILURE_RATE | 76.0% |
| STRATEGIC_DELTA_CHANGED | 23/25 |
| STRATEGIC_DELTA_UNCHANGED | 2/25 |
| INFORMATION_PRIORITY_RATE | 96.0% |
| INFORMATION_PRIORITY_SPECIFICITY | 96.0% |
| DECISION_DOMAIN_DIVERSITY | 2 |
| MECHANISM_DIVERSITY (archetypes) | {"Why this": 2, "Pricing": 22} |

## What did not improve

* `EVIDENCE_LED` is **0** on this cohort against **3** on the forty.
* One decision question covers 16 of 22 companies that reached one.
* 76.0% of readings are grounded on the company name alone (`NAME_ONLY`).

Grounding verdict, strategic delta and information priority **did
not exist** on the forty. A baseline of zero there is the absence
of a measurement, not a measurement of zero, and is not reported
as an improvement from zero.
