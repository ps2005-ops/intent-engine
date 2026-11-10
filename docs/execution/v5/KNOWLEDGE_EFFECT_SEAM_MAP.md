# The knowledge-effect seam

Built at founder `570abc5` → this commit, 2026-08-13 (Batch 15).
Backend: `CREDITS_EXHAUSTED` throughout.

## What was actually missing

Batch 14 found that nothing in production constructs a `KnowledgeEffect`.
Tracing one layer further found **why it could not**: the BEFORE state a
learning event needs was never recorded.

`decision_impact` ships the entire temporal comparison — `record_revision`,
`load_revisions`, `assess_against_prior`, `record_impact` — and every one of
them had **zero production call sites**. No revision was ever written, so no
second run could compare against a first, so no effect could exist. The
missing producer was one symptom; the missing *prior* was the cause.

Worse, the comparison production DID run is the one this module's own
docstring documents as broken: it grades the same analysis with the market
dossier against the same analysis without it, and the without side is empty on
every field — so every field reads empty → populated, nothing can grade NONE,
and the number is 100% by construction. That comparison answers "was the
dossier decision-relevant", which is a real question, and it stays. It cannot
answer "did we learn something".

## The chain, now

| stage | object | where |
|---|---|---|
| producer | `WebApp._record_learning` | `webapp/app.py` |
| comparison | `decision_impact.assess_against_prior` | temporal, prior revision as BEFORE |
| projection | `effect_producer.effects_from_impact` | `FieldDelta` → `KnowledgeEffect` |
| eligibility | `effect_producer.eligibility` | one gate, closed refusal vocabulary |
| persistence | `effect_producer.record_effects` | `reports/market/knowledge_effects.jsonl`, append-only |
| reload | `effect_producer.load_effects` | corrupt line skipped, never repaired |
| consumer | `learning_attribution.conversion` | reads the ledger, no longer `effects=()` |
| surface | founder dossier `learning_summary` | via `founder_demo_snapshot` |

**No second system of record.** One effect type (`learning_attribution`), one
comparison engine (`decision_impact`), one ledger.

## Effect vocabulary

Changing: `CREATED` `SUPPORTED` `WEAKENED` `CONTRADICTED` `REVISED`
`RESOLVED` `RETIRED`.

Non-changing, and mechanically distinct because they license different
actions:

| state | means | not to be confused with |
|---|---|---|
| `NO_CHANGE` | tested, and the state held | a re-read that tested nothing |
| `FIRST_OBSERVATION` | no prior existed; a baseline | an improvement |
| `UNMEASURABLE` | the test could not be run | no effect |
| `REFUSED` | the test should not have been run | no effect |

Refusal reasons are closed: `NO_COMPANY` `NO_ANALYSIS` `NO_PROVENANCE`
`CROSS_COMPANY_PRIOR` `INCOMPARABLE_WINDOW` `NOT_TESTABLE`.

## Two defects the build caught in itself

**Twelve effects per cycle.** `assess` returns a delta for all twelve impact
types, so one-effect-per-delta emitted eleven confirmations of components that
have never held content. The ledger would have filled with undisputable
confirmations and the conversion rate would have looked excellent — §16's
inflated-velocity implementation, arrived at by accident. Caught by the live
proof, not by a unit test. A component empty on both sides was not tested.

**A full stop reversed a claim.** `_norm` lowercased and collapsed whitespace
but left punctuation, so "Hold capacity." vs "hold capacity" graded `REVERSED`
— the strongest change signal there is. The module's contract says two
renderings of one claim are UNCHANGED; it was not true, and the moment a
comparison became a durable learning event it would have manufactured a
`CONTRADICTED` on every rerun where the model added a period.

## Live proof

`reports/v5/b15/KNOWLEDGE_EFFECT_LIVE_PROOF.json`. Evidence is SYNTHETIC and
marked so; the producer, comparison, eligibility, persistence, reload and
consumer are production objects and none is mocked.

```
first_observation      FIRST_OBSERVATION      (baseline, not improvement)
no_change              NO_CHANGE              (tested, held)
wording_only           NO_CHANGE              (no changing effect)
material_change        CONTRADICTED           (DECISION_CHANGING)
duplicate_replay       0 new rows             (ledger 4 → 4)
non_testable_reread    UNMEASURABLE           (no confirmation earned)
incomparable_window    REFUSED
cross_company_refusal  REFUSED
process_restart        0 new rows             (fresh interpreter)
conversion             MEASURED, 1/7 = 14.3%
```

What this **cannot** show: that a real analysis produces a real effect. That
needs the backend.
