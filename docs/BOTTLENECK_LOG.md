# Bottleneck log

One entry per improvement cycle. Each answers the same question before any
code is written: **is the thing I was about to build actually the highest-
leverage bottleneck?** The rule is that a bottleneck is *measured*, not
asserted — every entry carries the number that decided it.

Written newest-last, so the file reads as a history.

## Bottleneck half-life

The standing KPI for this phase. Markets are what the engine is learning
*about*; half-life is how fast it is learning **to improve itself**, which is
the thing that compounds.

> **Half-life** — the number of days a verified bottleneck stays the #1
> bottleneck before it is eliminated or overtaken.

A shrinking half-life means the loop is tightening. A growing one means
either the problems are getting genuinely harder or the measurement is getting
slower — and the two are told apart by whether the *metric* moved, not by
whether code shipped.

| # | Bottleneck | Discovered | Metric before | Root cause | Fixed | Metric after | Days as #1 |
|---|---|---|---|---|---|---|---|
| 1 | No evidence collected at all | 2026-07-30 | 0 evidence rows/company; 100% `no_strategic_reading` | `research_fn` was a placeholder returning `{}`; universe carried no `website` to research | 2026-07-30 | dated, source-classed evidence for 8/11 companies | **<1** |
| 2 | No outside source ever approved | 2026-07-30 | `independent_source` **0/11**; 3/3 readable tradables died at `no_outside_source` | `candidates[:8]` took discovery order; ~30 `company_owned` rank above 3 `customer_voice`, so outside sources were never approved | 2026-07-30 | `independent_source` 1/11; yield 36% → 45%; first company reaches the deepest gate | **<1** |

Both were found and closed inside a day, but neither is evidence of a fast
loop yet — they were both *self-inflicted*, introduced by the previous cycle
and caught by the next measurement. The number worth watching starts when a
bottleneck is external to the code just written.

---

## Cycle 1 — 2026-07-30

### What I was about to build

At the end of the previous cycle I asserted the next increment was a
**market-evidence adapter**, on the reasoning that `no_market_evidence` was the
gate blocking every WATCH record.

### What the measurement said

That was the right *observation* and the wrong *conclusion*. Three numbers,
all taken from the running system rather than from the code's intent:

| measurement | value | source |
|---|---|---|
| Companies in the universe | **5 total, 4 tradable** | `default_universe()` |
| Sectors covered | 3 (Technology, Consumer, Fintech) | same |
| Evidence produced per company in production | **0 rows, empty thesis** | `_env_research_fn`, hosted/context.py |

The mission requires 20–50 evaluated opportunities per day across large/mid/
small cap, growth/value, cyclical/defensive, and seven-plus sectors. The
system can currently evaluate four companies in three sectors.

More decisively: **`research_fn` returns `{"evidence": [], "thesis": ""}` in
production.** Every "WATCH / no_market_evidence" record I measured last cycle
came from an *injected test fake*. The real daily cycle produces four
`NO_TRADE / no_strategic_reading` rows, because there is no evidence to reason
over at all.

### Why the market adapter was the wrong next build

Compare the two candidates by what a day's learning would actually be:

| build | daily output | learning gained |
|---|---|---|
| Market-evidence adapter only | 4 companies × 0 evidence → 4 `no_strategic_reading` | **zero** — the market signal never gets consulted, because the reasoner exits at an earlier gate |
| Universe expansion only | 40 companies × 0 evidence → 40 `no_strategic_reading` | **zero** — a multiplier on nothing |
| **Company evidence collection** | 4 companies × real evidence → real readings | **non-zero, for the first time** |

The market adapter sits *behind* two gates the reasoner checks first
(`no_strategic_reading`, then `no_dated_evidence` / `no_outside_source`). Wiring
it while evidence collection returns nothing would have produced a component
that could not run, and a measurement that could not move — the definition of
building the wrong thing carefully.

Universe breadth is a real gap and is second, not first: it is a multiplier,
and the thing it multiplies is currently zero.

This also agrees with the prescribed build order — Stage 1 is *market evidence
collection* — which is a check on the reasoning rather than the reason for it.

### Decision

**Build the evidence collector, by wiring Founder Intelligence's real
ingestion into `research_fn`.**

Reuse, not new infrastructure: that pipeline is already built, already
production-verified, and already retrieves real public sources, parses them,
and derives dated observations with source classes. The call chain is
service-level and needs no webapp — `create_run → discover → approve →
compose_with_quality`, which is exactly what the web flow itself calls.

### What this cycle must respect

- **Provenance stays honest.** `create_run` and `approve` hardcode
  `actor_type="human"` because they were written for a founder clicking a
  button. An autonomous job recording itself as human would corrupt the audit
  trail. `actor_type` already permits `"system"`; both entry points take it as
  a parameter now, defaulting to `"human"` so the webapp flow is unchanged.
- **Known ceiling, stated up front.** Founder Intelligence's own measured
  limit is that roughly two companies in five yield a full strategic report;
  JS-rendered sites return metadata only (`/readyz` → `browser_rendering:
  false`). So this does not make every company reason — it makes *some*
  companies reason, where today none do.

### Expected measurable effect

Before: every production company → `NO_TRADE / no_strategic_reading`, quality 0.

After: companies whose sites are readable produce a dated, source-classed
reading and advance to a later gate. **The metric that must move is the
distribution of `blocked_by`** — specifically, `no_strategic_reading` falling
and later gates rising. If it does not move, the build failed regardless of
how much code it added.

### Measured result

Same universe, same day, placeholder `research_fn` versus the real one, run
offline against the company fixture:

| | `blocked_by` |
|---|---|
| Before | `no_strategic_reading: 3, not_tradable: 1` |
| After | `view_withheld: 1, no_strategic_reading: 2, not_tradable: 1` |

Per company, which is the clean measurement (see the caveat below), the gate
moved from `no_strategic_reading` with quality 0.0 to `view_withheld` with
real dated evidence and a non-zero quality. Stage 1 is operational: the
adapter returns dated, source-classed evidence rows from the real pipeline,
asserted by seven offline tests that run discovery, retrieval, parsing and
composition rather than a mock of them.

**Honest caveat on the sweep number.** Two of the three tradable companies did
not advance, and that is an artefact of the measurement, not a product defect.
`create_run` keys a run on `(domain, user_id, as_of)`, and the harness forced
all four companies onto the single fixture domain, so they collapsed into one
run and the later two reused the first's consumed approval. In production each
company has its own domain. The per-company result is the one to trust; the
sweep number understates the effect and is reported as measured anyway.

### What the build found on the way

The reasoner could not tell **"nothing was retrieved"** from **"plenty was
retrieved and the strategic gate correctly declined to read a strategy from
it."** Both reported `no_strategic_reading`. That made the whole `blocked_by`
distribution — the metric this cycle is judged on — undiagnosable, because the
two facts need opposite responses: fix the retrieval, versus do nothing at
all. Split into `no_strategic_reading` and `view_withheld`, which is what let
the measurement above show anything.

That defect was invisible until real evidence started flowing. It is the
argument for measuring after every build rather than reasoning about it.

### Next cycle's candidate (to be re-verified, not assumed)

Universe breadth: 4 tradable companies against a mission requiring 20–50 per
day across caps and sectors, and 3 sectors against a required 7+. It is now a
multiplier on something non-zero, which it was not before. **Do not build it
without re-running this analysis** — the Stage-1 work may have exposed a
larger constraint, and the point of this log is that the previous cycle's
"obvious next step" was wrong.

---

## Cycle 2 — 2026-07-30

### What I predicted, and why prediction is not measurement

I closed cycle 1 saying: *"`view_withheld` may turn out to be the dominant
gate, and that would make strategic-reading yield — not company count — the
real constraint."*

**Measurement disproved it.** Yield was not the binding gate, and neither was
universe breadth, the standing roadmap item.

### The instrument

Eleven offline company fixtures (`product_eval/sites.py`), each on its own
domain, run through the real ingestion and the real reasoner. Deterministic,
network-free, and deliberately including the hard cases: a blocked site, a
nonexistent company, two local businesses, and a site that argues with the
analyst. This replaced cycle 1's flawed harness, which forced every company
onto one fixture domain and collapsed them into a single run.

### Ranked bottlenecks

| rank | bottleneck | measurement | why ranked here |
|---|---|---|---|
| **1** | **No outside source is ever approved** | `independent_source` **0/11**. Every tradable company that formed a reading died at `no_outside_source` — **3 of 3** | A gate that can never pass. Not "fails sometimes": structurally unreachable, so no amount of upstream work could move it |
| 2 | Strategic-reading yield | 4/11 overall, 4/8 of those with evidence | Real, but it gates *some* companies. #1 gated **all** of them |
| 3 | Universe breadth | 4 tradable, 3 sectors vs 20–50/day and 7+ sectors | Still a multiplier — and multiplying a pipeline that cannot reach a position just produces more WATCH rows |
| 4 | Retrieval on JS-rendered sites | 3/11 produced no evidence | Known, external, unchanged |

### Root cause of #1

Not a missing capability — discovery **was** finding outside sources, for
every single company:

```
candidate source_classes: {company_owned: 30, executive_statement: 2,
                           investor_material: 2, customer_voice: 3}
retrieved doc source_classes: {company_owned: 3, executive_statement: 1,
                               investor_material: 1}
```

The `customer_voice` candidates were discovered and never approved, because
my own cycle-1 adapter approved `candidates[:8]` — the first eight in
discovery order, which are all company pages. **A one-line slice made the gate
it was feeding impossible to pass.**

### Fix

`select_diverse`: round-robin across source classes, outside classes drawn
first so they cannot be crowded out, discovery order preserved *within* a
class because that ranking is the ingestion layer's judgement.

### Measured effect

| metric | before | after |
|---|---|---|
| `independent_source` | **0/11** | 1/11 |
| strategic-reading yield | 4/11 (36%) | **5/11 (45%)** |
| yield among companies with evidence | 50% | **62%** |
| view-withheld rate | 4/8 | 3/8 |
| Shopify: gate → quality | `no_outside_source` → 0.525 | **`no_market_evidence` → 0.80** |

Shopify is the first company in the corpus to reach the deepest gate in the
pipeline: a dated, independently-corroborated reading with nothing left
blocking it but the market signal.

**Why 1/11 and not more, stated honestly.** Palantir and Sony still report
`no_outside_source`. Their fixtures *declare* customer-voice candidates but do
not serve those URLs, so retrieval 404s. That is the fixture having no outside
source to find, and `no_outside_source` is then the correct answer rather than
a defect. The fix works where an outside source actually exists; it cannot
invent one.

### Bottleneck ranking after this cycle

1. **Strategic-reading yield** — 3 of 8 companies with evidence still produce
   no view. Now the top gate for companies that have evidence.
2. **Universe breadth** — unchanged, and now genuinely a multiplier on a
   pipeline that can reach the deepest gate.
3. Market-evidence adapter — reachable for the first time, and therefore no
   longer speculative to build.

**Do not treat #1 as decided.** Two cycles running, the measurement has
overturned the predicted next step.

---

## Engineering prediction accuracy

The engine should get better at predicting the impact of its own engineering,
not only at reading markets. Recorded per cycle, before the build.

| cycle | predicted #1 | actual #1 | predicted gain | actual gain | error | root cause of the error |
|---|---|---|---|---|---|---|
| 1 | market-evidence adapter | evidence collection returns nothing | — (no metric named in advance) | `no_strategic_reading` 3→2, yield 0→36% | **wrong bottleneck** | Reasoned from the gate I could *see* (`no_market_evidence`) without checking that the records showing it came from an injected test fake, not production |
| 2 | strategic-reading yield | no outside source ever approved | — (no metric named in advance) | `independent_source` 0/11→1/11, yield 36%→45% | **wrong bottleneck** | Read a metric (`no_outside_source`) as a fact about the world — companies lack independent coverage — instead of inspecting the stage before it, where the candidates were present all along |
| 3 | strategic-reading yield *(carried from cycle 2)* | **market-evidence adapter** | LV 0 → **1–3** | LV 0 → **1** | **correct, at the floor** | First cycle with a stated numeric prediction, and the first correct one. Landed at the floor for the reason given in advance: only Shopify clears every earlier gate |
| 4 | resolution / outcome scoring | **the objective function itself** | — | LV shown gameable 0→10 by one constant; replaced | **wrong bottleneck** | Ranked features behind the metric without testing whether the metric survived being made a target. A one-day-old KPI is the least-tested component in the system, not the most trusted |

Cycles 1 and 2 named no numeric prediction in advance, so their error is
recorded as categorical (wrong bottleneck) rather than as a magnitude. Cycle 3
is the first with a stated numeric prediction, which is what makes an error
bar possible at all.

**Pattern across three cycles.** Every wrong prediction has the same shape: a
terminal gate was read as a *finding about the domain* when it was a *finding
about the stage before it*. The correction each time came from measuring one
layer upstream. That is now the first thing to check, not the last.

---

## Cycle 3 — 2026-07-30

### Learning Velocity, defined so it can be measured

> **LV — the number of evaluations produced per cycle that can EVER yield a
> right/wrong verdict.**

An evaluation that can never be graded accumulates; it does not teach. This
definition is deliberately harsh on volume: a hundred WATCH records with
excellent reasoning have an LV of zero, because nothing in them will ever be
confirmed or refuted.

### Measured

```
evaluations produced       : 11
RESOLVABLE (can be graded) :  0
LEARNING VELOCITY          :  0
terminal classification    : {WATCH: 3, NO_TRADE: 8}
```

**LV is zero and has been zero for the entire phase.** Every path terminates
unresolvable. The loop is open: records accumulate and nothing ever tells the
engine whether it was right.

### Second-order thinking overturns the carried prediction

The ranking said strategic-reading yield. Applying "if this bottleneck
disappears, what becomes the next one?":

| candidate | if fixed perfectly | resulting LV |
|---|---|---|
| Strategic-reading yield | the 3 companies with evidence and no view advance — to `no_outside_source` or `no_market_evidence`, still WATCH | **0** |
| Universe breadth ×10 | 110 evaluations instead of 11, all still WATCH/NO_TRADE | **0** |
| **Market-evidence adapter** | BUY/SELL becomes reachable → prediction → resolution → calibration | **> 0** |

Two of the three top-ranked bottlenecks have a measured expected LV gain of
**exactly zero**. They make the system better at producing records it can
never grade. Only closing the loop moves LV off zero, and nothing downstream
of it — post-mortems, calibration, knowledge extraction, weekly meta-review —
can exist until it does.

This is the third cycle running in which the predicted next bottleneck was
wrong. It is the first in which the LV metric caught it *before* any code was
written rather than after.

### Prediction for this cycle — recorded before implementation

**Hypothesis.** LV is zero because no component supplies market evidence, and
the reasoner correctly refuses to invent a direction from a strategic thesis.
Supplying an explicitly-labelled baseline signal closes the loop.

**What will be built.** A momentum baseline over real price history — not a
claim of skill. Its purpose is to make predictions *resolvable*, establish the
bar any future signal must beat, and generate the ≥30 resolved predictions
that `A-M5` requires before any accuracy claim is permitted. It is the on-ramp
to calibration, not an attempt at alpha.

**Predicted metric movement:**

| metric | now | predicted after |
|---|---|---|
| Learning Velocity (gradable/cycle) | 0 | **1–3** |
| companies reaching BUY/SELL | 0 | 1–3 |
| terminal gate `no_market_evidence` | 1 | 0 |

Prediction is deliberately narrow: only Shopify currently clears every earlier
gate, so 1 is the floor. Sony and Palantir would join only if they also clear
`no_outside_source`, which they do not. **Predicting >3 would be predicting a
fix to a different bottleneck.**

**Expected downstream effect.** Resolution, post-mortems and calibration
become buildable for the first time — they are currently unbuildable, not
merely unbuilt.

**Expected risk.** A baseline with no demonstrated edge will produce wrong
predictions. That is acceptable and is the point: a wrong resolved prediction
has strictly more learning value than an ungradable WATCH. The risk to guard
is not being wrong — it is the baseline being *mistaken for skill*, which is
why the signal source is recorded on every opportunity and labelled
unvalidated.

### Measured result — predicted vs actual

| metric | before | predicted | **actual** |
|---|---|---|---|
| Learning Velocity (gradable/cycle) | 0 | 1–3 | **1** |
| companies reaching BUY/SELL | 0 | 1–3 | **1** (Shopify, via `baseline_momentum.v1`) |
| terminal gate `no_market_evidence` | 1 | 0 | **0** |

**Prediction correct, at the floor of the stated range** — and for the reason
given in advance rather than by luck: only Shopify clears every earlier gate,
so 1 was named as the floor and 3 would have required Sony and Palantir to
also pass `no_outside_source`, which they do not. Predicting more would have
been predicting a fix to a different bottleneck.

**Learning Velocity is non-zero for the first time in the phase.** The loop is
closed: an evaluation now exists that will eventually be graded right or
wrong.

### What this does and does not claim

It does not claim skill. `baseline_momentum.v1` is a momentum rule with a
stated prior of 0.55 and no demonstrated edge, and every record it produces
carries `market_source` so calibration can hold it to its own account rather
than averaging it in with whatever replaces it.

Its value is that it is a *baseline*: without one, "our signal is good" is
unfalsifiable, because there is nothing it had to beat. And it is the on-ramp
`A-M5` requires — accuracy claims are gated behind ≥30 live-resolved
predictions, and there is no route to thirty resolutions without first making
predictions that resolve.

### Bottleneck ranking after this cycle

1. **Resolution and outcome scoring** — LV is 1 per cycle, but nothing yet
   *grades* the prediction. Until resolution runs, LV is potential rather than
   realised. This is now the highest-leverage item by the same argument that
   promoted the market signal: everything downstream is unbuildable without it.
2. **Universe breadth** — finally a true multiplier. Every company added now
   has a path to a gradable evaluation, which was not true in cycles 1 or 2.
3. **Strategic-reading yield** — 3 of 8, ranked #1 by the previous cycle and
   demoted twice by second-order analysis. It produces better WATCH records,
   not gradable ones.

### Second-order check on that ranking

If resolution existed, the next binding constraint would be **sample size**:
one gradable evaluation per cycle needs thirty cycles to reach the A-M5
threshold. That argues universe breadth becomes #1 immediately after
resolution — the first time in the phase it will have been the right answer.
Recorded now so the next cycle can test it rather than rediscover it.

---

## Cycle 4 — 2026-07-30 · the metric was the bottleneck

### Measured first, on the metric itself

Cycle 3's Learning Velocity was one day old. Rather than rank features, this
cycle applied the metric-integrity test to LV. It failed:

| `MIN_ABS_RETURN` | Learning Velocity |
|---|---|
| `0.02` (shipped) | 0 |
| `0.0001` (one edit) | **10** |

Ten companies moving inside the noise floor. Same evidence, same reasoning,
same prices — LV rose 10× for a system that had become **worse**, since it
would now be predicting noise confidently. Full write-up in
[`METRIC_INTEGRITY.md`](METRIC_INTEGRITY.md).

**The highest-leverage bottleneck was the objective function**, not any
feature behind it. A wrong objective misdirects every future cycle, so its
expected cost compounds faster than anything it would have ranked.

### Learning Value replaces Learning Velocity

Weighted by resolution quality × information gain × novelty × calibration
impact — with a hard rule: **three of those four cannot be measured today and
are therefore not estimated.**

Zero predictions have resolved, there is no knowledge base, and `A-M5` gates
calibration behind ≥30 resolutions. Implementing the full formula with guessed
factors would be strictly worse than the metric it replaces: moving LV costs a
code edit; moving a self-assigned factor costs an opinion. Unmeasurable factors
return `UNMEASURABLE`, and the score **refuses to produce a number** while any
are missing — because a partial product silently treats unknown as 1.0, which
makes an unmeasured system score like a fully-understood one.

### Novelty, and the correction it needed

Novelty is measurable now and is the factor that guards the quantity-over-
quality failure. The first implementation used flat tiers and **failed the
motivating case**:

| | resolvable | novelty-weighted (v1) | novelty-weighted (final) |
|---|---|---|---|
| A: 100 momentum trades | 100 | 50.5 ❌ | **5.19** |
| B: 20 varied evaluations | 20 | 12.0 | **9.13** |
| gaming: same trade ×10 | 10 | — | **1.55** |

Flat per-company credit still let A win. Fixed with harmonic decay within a
shape — `1/(1+k)` — chosen because that is how repeated sampling of one
hypothesis behaves, not because it produces a preferred ordering. A hundred
repeats are now worth about five first attempts.

### Opportunity coverage

Measured on the real universe, and it found a blind spot the engine could not
see about itself:

```
counts: {sector: 3, industry: 4, market_cap: 0, region: 0}
sector concentration: 0.5
gaps: 8 of 10 sectors, ALL market caps, ALL regions
```

`market_cap` and `region` read **0 because those fields do not exist on
`CompanyProfile`**. The engine cannot measure its own coverage on two of five
dimensions. Reported as gaps rather than a score, deliberately — "no
healthcare, no small-cap, no international" names the next companies to add;
"coverage 0.4" invites optimising the number.

### Ranking after this cycle

1. **Resolution and outcome scoring** — unchanged at #1. Three of four Learning
   Value factors turn on the moment outcomes exist. It is the single change
   that unblocks the most measurement.
2. **Universe breadth, now with coverage targets** — no longer "add companies"
   but "add the eight missing sectors, and add the `market_cap` and `region`
   fields so the gap can be measured at all".
3. Strategic-reading yield — unchanged, still producing better WATCH records
   rather than gradable ones.

### Prediction for the next cycle — recorded now

Resolution will move `resolution_quality` from `UNMEASURABLE` to measurable
for **1** evaluation (the single baseline BUY), leaving Learning Value still
unscored because `information_gain` and `calibration_impact` need a knowledge
base and ≥30 resolutions respectively. **Predicted: LV score remains `None`,
`unmeasurable_factors` drops from 3 to 2.** If it returns a number, something
has been faked.
