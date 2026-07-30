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
