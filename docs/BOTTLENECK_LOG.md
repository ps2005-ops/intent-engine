# Bottleneck log

One entry per improvement cycle. Each answers the same question before any
code is written: **is the thing I was about to build actually the highest-
leverage bottleneck?** The rule is that a bottleneck is *measured*, not
asserted — every entry carries the number that decided it.

Written newest-last, so the file reads as a history.

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
