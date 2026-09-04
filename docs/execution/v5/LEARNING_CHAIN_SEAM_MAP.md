# The canonical learning chain, seam by seam

Traced at founder `46027cc` / market `fbcbacc`, 2026-08-13 (Batch 14).

The question this answers is not "does the code exist" but "does anything
carry a value through it". Every seam is classified by what is actually true
at the call site, not by what a module is capable of.

| state | means |
|---|---|
| `LIVE` | a producer writes, something reads, and it ran on the frozen ten |
| `WIRED_NOT_EXERCISED` | reader and writer both exist; no value has crossed |
| `BLOCKED_DATA` | needs data this deployment does not hold |
| `BLOCKED_EXTERNAL` | needs a dependency outside this system (credits) |
| `MISSING` | nothing in this codebase can produce it |

## The chain

| # | seam | producer | consumer | state |
|---|---|---|---|---|
| A | canonical evidence | `company_ingestion.service` | analyst, dossier, wave | **LIVE** |
| B | evidence independence / origin | `company_ingestion.independence` | selection, dossier, wave, **critic (new)** | **LIVE** |
| C | analyst interpretation | `strategic_intelligence.analyst.runner` | report | **BLOCKED_EXTERNAL** — 9/10 |
| D | belief formation | — | — | **MISSING** |
| E | belief revision | — | — | **MISSING** |
| F | expectation preregistration | — | — | **MISSING** |
| G | expectation reconciliation | — | — | **MISSING** |
| H | thesis formation / revision | report `hypotheses`, `shifts` | dossier | **BLOCKED_EXTERNAL** |
| I | causal estimate / update | — (market-side only) | — | **MISSING** on founder |
| J | hidden-state / world model | — (market-side only) | — | **MISSING** on founder |
| K | research priority | `readiness`, `research_modes` | report | **LIVE** |
| L | knowledge effects | — | `learning_attribution` reads | **MISSING** |
| M | learning attribution | `company_ingestion.learning_attribution` | wave, dossier | **WIRED_NOT_EXERCISED** |
| N | founder dossier consumption | `demo_dossier.assembler` | dossier surfaces | **LIVE** |

## The finding that changes the next batch

**Seam L has no producer.** `grep "effect_type\s*[=:]"` across `src/` returns
exactly one hit — the dataclass field declaration itself. Nothing constructs a
`KnowledgeEffect` anywhere in production, and both call sites of
`learning_attribution.conversion(...)` pass `effects=()` as a literal.

Batch 13 reported criterion 10 as MET-as-`BLOCKED_EXTERNAL_CREDITS`, which
reads as "credits are the only barrier". They are not. **Restoring credits
would move the wall from `ELIGIBLE_COMPANIES → ANALYZED` to
`ANALYZED → BELIEF_ELIGIBLE`, and that wall is `NO_PRODUCER`, not blocked.**

The funnel already shows this on the frozen ten. Nine companies never reached
an analysis; the one that did starved at the very next step, and its cause is
not credits:

```
DISCOVERED                     140
FETCHED                         68   (48.6%)
CANONICALIZED                   71   (104.4%)
INDEPENDENT                     22   (31.0%)
ELIGIBLE_COMPANIES              10   [companies, new population]
ANALYZED                         1   (10.0%)      <- BLOCKED_EXTERNAL
BELIEF_ELIGIBLE                  0   [evidence_rows, new population]  <- NO_PRODUCER
BELIEF_CHANGED                   0
THESIS_OR_EXPECTATION_CHANGED    0
EXECUTIVE_CONSUMED              10
```

per-company first starved transition:

```
 6  ELIGIBLE_COMPANIES → ANALYZED   [BLOCKED_EXTERNAL]
 2  CANONICALIZED → INDEPENDENT     [HEALTHY]
 1  DISCOVERED → FETCHED            [HEALTHY]
 1  ANALYZED → BELIEF_ELIGIBLE      [NO_PRODUCER]
```

## Where a producer could attach

The founder path has no belief object, so there is nothing whose state changes
for an effect to point at. It does have one real state-change seam already
built and working: **dossier revision**. `external_intel.decision_impact`
compares a company's previous revision against the current one over SEMANTIC
fields, handles `FIRST_OBSERVATION` as neither impact nor non-impact, and
persists to `reports/market/dossier_revisions.jsonl`.

That is where evidence → knowledge attribution can attach without inventing a
second belief system: target type `FOUNDER_DECISION_COMPONENT`, before/after
from the semantic field diff, evidence ids from the citations behind the
changed field. It needs two revisions to have a before, so it needs one
analysis that completes — which needs credits.

**Order matters: the producer is the blocker, credits are the precondition.**
Building the producer first means the first paid run measures something.

## Learning acceleration record

| iteration | batch | defect | repair | before → after | next bottleneck |
|---|---|---|---|---|---|
| 0 | 12 | 404s from guessed paths took approval slots | attested `homepage_link` over guessed `known_path` | yield 40.0% → 46.4%; independent share UNAVAILABLE | independence unmeasured |
| 1 | 13 | independent slot lost to a guessed review URL; origin read as host | attested filings promoted; origin = filer | independent docs 9 → 22; share 12.5% → 31.0%; `INDEPENDENT_EXTERNAL_SOURCE` 0 → 15 | evidence not consumed by reasoning |
| 2 | 14 | origin independence never reached reasoning; critic's own looser copy of "independent" | critic reads canonical classes and counts ORIGINS | two live gate defects closed; funnel instrumented | **seam L has no producer** |

Iteration 2 exposed a new bottleneck and it is recorded rather than repaired:
building the effect producer is a vertical of its own, and the measured claim
of this batch is that it — not credits — is what criterion 10 now waits on.
