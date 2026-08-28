# Decision value — the methodology and the numbers

*Canonical. `reports/decision_value.json` and `reports/product_parity.json`
are the records; this explains what they measure and why the measure is
shaped the way it is.*

---

## The question

Does the economic world model change a **decision**, or only the prose?

A prose diff cannot answer it: a synonym, a reordering, an extra macro
paragraph all register as change. So the fields a founder acts on are **enums
and identifiers, not sentences** —

    action           one of a fixed vocabulary
    top_priority     a channel id
    risk severity    an ordinal
    scenario band    an ordinal
    confidence       an ordinal

A wording change literally cannot move any of them. Materiality does not have
to detect prose and refuse it; it cannot see prose at all.

`MATERIAL_FIELDS` and the rubric were frozen before any pair was scored, and
`assert_rubric_unchanged` refuses a run whose rubric hash has moved — editing
the measure afterwards is choosing it with the answer in view.

## Baseline A is a real analysis

§3 is the load-bearing requirement. A is not a stub: it reads the company's
own structural economics and produces a genuine recommendation.
`assert_baseline_is_real` refuses an A with no risks, because `top_risks` and
`risk_severity` are two of the seven material fields and both are computed
from them — an A with none concedes them before the comparison starts.

On the live path A has three sources, in order: the report's
**vulnerabilities**; its **blind spots**, gated to tensions this business
model can actually have; and the company's **own stated exposures**, read out
of its filings. The third is the only one that is never library text.

## The result

| | |
|---|---|
| A/B comparisons | **60** |
| material DecisionDelta | **25** (41%) |
| attributable | **25 / 25** |
| MATERIAL_BUT_UNATTRIBUTED | 0 |
| NO_MATERIAL_ECONOMIC_DELTA | **35** (58%) |
| DecisionDamage | **0** |
| negative control | **PASS** |

Ten companies across six regimes, the regimes chosen by asking the
contemporaneous classifier which origins it reads that way rather than by
remembering which years felt like what.

**The abstention rate is the result worth having.** The negative control
confirms the model both speaks and stays quiet within every regime; a system
that changed every analysis in every regime would be over-injecting, not
informing.

## What a zero from the damage detector means

`DecisionDamage = 0` is only evidence if the detector can fire. Three of the
eight originally declared kinds — `FALSE_SPECIFICITY`, `WRONG_EXPOSURE`,
`GENERIC_RECOMMENDATION` — had no detector referencing them at all, so the
zero was in part a statement about a tuple.

All **11 of
11** declared kinds
now have one, `damage_coverage()` reports which, and the closure
reconciliation refuses a zero from a vocabulary with dead entries.
`tests/test_damage_detector_adversarial.py` attacks every detector with a
case built to trigger it, and pins that a *uniform* count — every material
case producing exactly one damage of one kind — is refused as an instrument
tell rather than accepted as a finding.

## Product parity

The same sixty cases run through the **product consumer**, compared case by
case against the research harness. Not a prose diff — the two paths compose
different sentences by design. The comparison is on the structured verdict.

| | |
|---|---|
| cases | 60 |
| identical verdict | **52** |
| explained divergence | 8 |
| **unexplained divergence** | **0** |
| **unsupported new delta** | **0** |
| material but unattributed | 0 |

Every explained divergence is one shape: the product knows something the
research arm does not — a business model with no mechanism for the condition
that fired, or a canonical sign where the research arm's hand-written note
says MIXED.

## Break proofs

| wave | caught | tautologies |
|---|---|---|
| research (16 proofs) | 16/16 | 0 |
| product (26 proofs) | 26/26 | 0 |

The meta-guard refuses a proof whose mutated symbol IS the guard under test,
before it runs. Thirteen tautological proofs were written by hand across
three earlier runs; none can be written now.

## What this does NOT establish

Not proven ROI, not proven revenue lift, not proven forecasting superiority,
not calibrated forward accuracy. What is established is evidence use,
attributable decision change, selective abstention, provenance,
falsifiability, information prioritisation, self-correction and forward
preregistration. The rest requires evidence that has not happened yet.
