# The economic world model, wired into the product

*Branch `v6/unified`. This document records the PRODUCT run: what was wired,
what the wiring broke, what was found live, and what is still not proven.*

---

## What this run was for

The previous run ended with a working economic world model and an honest
sentence about it:

> `worldmodel`, `founder_ab`, `forward_engine`, `forward_ledger` and
> `breakproof` are **not imported by the webapp**. Deploying would only prove
> the existing surface still works — that isn't the claim §31 asks for.

So the research/product boundary was the highest-priority defect, and closing
it was the whole job: one vertical seam from the shared economic state to a
sentence a founder reads, deployed, driven against real companies, broken,
repaired and re-proven.

---

## The seam

```
econ.state (shared, public, dated)
    -> external_intel.econ_context        readings
    -> external_intel.econ_decision       the join: state x exposure x mechanism
    -> econ.founder_contract              FounderEconomicContext
    -> founder_brief.dossier              the ECONOMIC IMPACT passage
       founder_brief.qa                   the CEO answers
       webapp.app                         one object per request, memoised
```

The import direction is unchanged and still asserted:
`tests/test_econ_core_is_neutral.py` forbids `econ` from importing either
product, and `founder_contract` is a dataclass module that imports nothing but
`econ.vocabulary`. The founder side consumes the neutral contract; the neutral
core never learns that a founder exists.

### One object, not three derivations

`FounderEconomicContext` is built once per request and memoised on the
per-request thread-local — cleared at the top of `_route` beside the other
memos, because a memo that survives a request is the previous visitor's
company. The brief, the full analysis and the CEO Q&A render *that object*.

§21 — "brief and full may not contradict" — is therefore a property of there
being one object, not of three renderers agreeing. Every previous split in
this product (the brief contradicting the primary screen; Q&A denying a
falsifier step 1 was showing) looked correct on each surface alone.

### What the contract refuses, at construction

| refused | why |
|---|---|
| collective-human constructs | zero of sixteen are PROMOTED; the register is FROZEN_CANDIDATE |
| rehearsal expectations | REHEARSAL proves machinery; it is not a track record |
| a calibration claim with nothing resolved | an accuracy figure with an empty denominator |
| a stale state carrying a material change | §17 |
| a freshness that disagrees with its own dates | added after break proof 8; see below |
| COMPLETE with nothing in it | a heading with no content |
| NO_MATERIAL_ECONOMIC_DELTA carrying a change | a reader cannot tell which is true |

---

## What the parity harness found

`scripts/run_product_parity.py` runs the same sixty A/B cases through the
**product consumer** and compares the verdict case by case against the
research harness. It is not a prose diff — §20 says explicitly that the two
paths compose different sentences by design. It compares the structured
verdict: material stays material, abstention stays abstention, and no
unsupported new delta appears.

It found four things, in this order.

**1. The product was louder than its own research.** 38 material deltas
against 24. It treated any adverse-direction move as adverse; the research arm
had declared a 3% threshold before scoring anything. Same threshold now,
declared in one place.

**2. Which way is adverse is a company fact, not a channel fact.** One sign
per channel told Walmart that rising inflation hurt it, in four of six
regimes — while Walmart's own mechanism says grocery inflation *widens the
everyday-low-price advantage*. The sign now comes from
`company_profile.adverse_direction_for`, keyed on **(channel, business
model)** — the same key as the mechanism, so the two cannot disagree. A pair
whose mechanism states both directions carries **no sign** and can never move
a recommendation. That absence is the design, not an omission.

**3. The research harness's own convention was inverted on demand channels.**
Traced empirically rather than argued: every channel resolved to "adverse when
the driver rises", which is right for unemployment and credit spreads and
backwards for consumption, industrial production and permits. Nike's mechanism
says weaker consumption hits units; falling consumption scored as *not*
adverse for Nike. Union Pacific's says carloads follow permits; rising permits
scored as adverse for it. Corrected at source — the fourth element of a
`COMPANIES` channel now says which way the DRIVER has to move to hurt — and
re-run.

**4. Two coverage gaps that made real companies structurally unreachable.**
`SCALE_RETAIL` is a class the validation manifest carries and the transmission
table did not, so a scale retailer received no economic reading at all. And
the curve slope and the credit spreads were folded into `MARKET_RATE`, whose
sign for a balance-sheet business is deliberately unestablished — so a **bank
could never receive an economic reading**, which is the clearest case there is
of a condition reaching a business through a named mechanism.

### The offline numbers, after the corrections

| | research arm | product consumer |
|---|---|---|
| cases | 60 | 60 |
| material DecisionDelta | 25 | 19 |
| attributable | 25 / 25 | 19 / 19 |
| abstained | 35 | 41 |
| DecisionDamage | 0 | 0 |

| parity | |
|---|---|
| identical verdict | **52** |
| explained divergence | 8 |
| **unexplained divergence** | **0** |
| **unsupported new delta** | **0** |
| material but unattributed | 0 |

The eight explained divergences are all one shape: the product knows something
the research arm does not. Six are companies whose business model has no
mechanism for the condition that fired (including Meta, which the manifest
does not classify, and which therefore abstains rather than guessing). Two are
NVIDIA, where the research arm's hand-written note calls its
industrial-production exposure MIXED and the canonical
`DESIGN_AND_MANUFACTURE` table signs it — §9 says the reasoning must come from
canonical exposure state, so the product's source is the sanctioned one.

---

## Break proofs

Sixteen new mutations, against the code that runs when a customer presses
Analyse: the router, the context producer, the dossier renderer, the Q&A
router, the durable store.

**16/16 CAUGHT. 0 REFUSED_TAUTOLOGY. 0 NOT_CAUGHT.**
Target kinds: 8 producer, 3 consumer, 2 renderer, 2 call site, 1 persistence.

The mirror carries the **tests** as well as `src`, because several guards here
are structural — "is the renderer handed the context at all" cannot be a
runtime check, since a surface that was never handed it renders a
complete-looking page. A structural test resolving paths against the
repository would read the unmutated file and report green for a mutation it
never saw, so every path is derived from the imported module's own
`__file__`.

Two of the sixteen found real holes rather than confirming a guard.

**Proof 8 — a context could be *told* it was fresh.** The mutation computed
the age against the state's own date instead of the run's, so a 601-day-old
reading arrived labelled CURRENT. The admission wall, the damage detector and
the staleness rule all then worked *correctly* on a false input. The contract
now recomputes freshness from the two dates it carries and refuses a producer
that disagrees — the one place that has both dates and no reason to prefer
either answer.

**Six proofs were refused, and the meta-guard was right to.** They named a
test file as the production call path, and `assert_call_path_exists` reported
that the file "never calls" the test in it. True, and not the question: a
pytest test is invoked by collection, so its definition in a collected file is
its call site. The check now accepts a test definition. §36's anti-tautology
rule (`mutated_symbol != guard_under_test`) is unchanged and still separate.

---

## Failure semantics, preserved

Seven states, and the two that look like nothing are the two that matter most.

| state | what the reader is told |
|---|---|
| `COMPLETE` | the n elements of the recommendation that changed, and why |
| `NO_MATERIAL_ECONOMIC_DELTA` | "Current economic conditions do not materially change the strategic recommendation for this company", then the analysis continues |
| `INSUFFICIENT_EVIDENCE` | this company has no evidenced exposure to anything the state measures — a gap in its exposure map, not a quiet economy |
| `BLOCKED_DATA` | no state is published to this deployment; the analysis rests on the company's own evidence |
| `BLOCKED_EXTERNAL` | the state could not be read; reported as unavailable rather than omitted |
| `NO_NEW_DATA` | the state has not moved |
| `FAILED` | reported as failed rather than omitted |

An abstention renders one line and stops. It does not become a missing
section, and it does not grow a macro paragraph to justify its own heading — a
section that always speaks teaches its reader to stop reading it.
