# V5: does the world model change a decision, or only the prose?

**From:** `82e93726` on `v6/unified`
**Rubric:** `15f463e9e671cb03`, frozen before a single A/B pair was scored.

---

## The measurement that was invalid, replaced

`DecisionDelta = 10/10` was scored against a constant placeholder — every
field differed by construction. It is marked
`INVALID_COMPARATOR_FOR_PRODUCT_VALUE` and is never reported as product
evidence again.

**Baseline A is now a real analysis.** It reads the company's own structural
economics — grocery mix for Walmart, deposit beta for JPMorgan, backlog
conversion for Caterpillar — and produces a genuine recommendation without any
macro reading. `assert_baseline_is_real` refuses a stub, and break proof 14
found a hole in that guard: an A with a priority and an information request but
**no risks** was passing, and two of the seven material fields are computed
*from* the risks. Tightened.

**The decision fields are enums and identifiers, not sentences.** `action`,
`top_priority`, severity, scenario band, confidence. A wording change cannot
move any of them, so materiality never has to detect prose and refuse it — it
cannot see prose at all.

---

## 60 comparisons: 10 companies × 6 regimes

Regimes chosen by asking the contemporaneous classifier which origins it reads
that way, not from memory.

| | |
|---|---|
| material DecisionDelta | **24 (40%)** |
| attributable | **24 (100% of material)** |
| MATERIAL_BUT_UNATTRIBUTED | 0 |
| NO_MATERIAL_ECONOMIC_DELTA | **36 (60%)** |
| DecisionDamage | **0** |
| negative control | **PASS** |

The 60% abstention rate is the result worth having. A system that changed every
analysis in every regime would be over-injecting, not informing — §15 counts
`NO_MATERIAL_ECONOMIC_DELTA` as a success, and the negative control confirms
the model speaks in some cases and stays quiet in others *within every regime*.

### The damage detector was broken, and said so

It first reported **24 damages, all EXCESSIVE_CONFIDENCE, exactly equal to the
material count** — a uniform result is an instrument tell. It compared
`provenance_coverage`, a *ratio* already saturated at 1.0 in Baseline A, so it
could never improve and fired every time. Rewritten to compare the **count of
grounded observations**; it now reports 0 and is proven still able to fire.

---

## Relations: a lag that has not elapsed is not a failure

The previous run's bleed detector compared year-on-year changes with **no lag
check** and reported 4 of 6 relations as non-firing. With `RelationCheck`:

| state | count |
|---|---|
| SUPPORTED_PREDICTIVE | 1 |
| CANDIDATE (driver did not move enough) | 5 |
| CONTRADICTED | 0 |

Five relations are `CANDIDATE` because their **drivers did not move**, not
because the mechanism failed. `assert_lag_respected` refuses to score a
relation as contradicted before its lag has elapsed.

## Dimensions: LIVE is not useful

| quality | count |
|---|---|
| LIVE_DECISION_RELEVANT | 6 |
| LIVE_CONTEXT_ONLY | 3 |
| LIVE_UNPROVEN_VALUE | 2 |
| BLOCKED | 6 |

None of the six blocked dimensions blocked a material decision in 60
comparisons, so **none was unblocked**. §17: fix only what blocks a measured
decision.

---

## §36 — the meta-guard, machine-enforced

Across three runs, **thirteen break proofs** were written as: mutate the guard,
then call the guard. Every one reported NOT_CAUGHT and was diagnosed by hand.
Noticing the same error three times without preventing it is itself the defect.

`breakproof.Proof` now requires every proof to declare `mutated_symbol`,
`guard_under_test` and `production_call_path`. `validate()` **refuses the proof
before it runs** when the first two are the same symbol — seeing through module
prefixes, so `WM.assert_no_double_count` and `assert_no_double_count` are
caught as identical. `assert_call_path_exists` **parses** the call site rather
than grepping it, because a docstring documenting a guard is not a call to it.

> **16/16 CAUGHT, 0 REFUSED_TAUTOLOGY.** Target kinds: 10 producer,
> 2 persistence, 2 consumer, 1 renderer, 1 call site. Not one assertion helper.

---

## The stagnation detector caught the report

It flagged `EXPECTATION_STAGNATION` — drivers moved and no expectation opened.
That was real: §19's generator did not exist. I implemented it rather than
widening the detector. One expectation opened from the single
`SUPPORTED_PREDICTIVE` relation (MORTGAGE30US → PERMIT, driver +0.12, lag
elapsed); five relations skipped as not qualifying. Forward ledger: **13 open**.

Then it flagged the same alert again — because the report was passing
`expectations_opened=0` as a *literal*. Fixed to read the ledger. Now
`LEGITIMATE_STABILITY`.

---

## LIVE: not attempted, and why

The modules this run and the last one built — `worldmodel`, `founder_ab`,
`forward_engine`, `forward_ledger`, `breakproof` — are **not imported by the
webapp**. `test_econ_core_is_neutral` forbids the econ core from importing
either product, and nothing on a deployed path consumes them.

Deploying would prove the existing surface still works, which is not the claim
§31 asks for. Reporting `LIVE_PROVEN` from that would be false.

**The wiring gap** is a founder surface that renders `EconomicState`, the A/B
decision delta and the forward ledger status. That is the top-ranked next task,
and it is product work rather than research.
