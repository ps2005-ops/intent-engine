# Research asset ledger

What durable knowledge this project has created — as distinct from what it did
on any given day. Operational metrics reset; these do not.

A research asset is a finding that **changes what future work should do**. A
day that produces none is an operating day, not a research day, and both are
legitimate.

---

## Validated negative results

Hypotheses confidently ruled out. Each cost real measurement and none needs
repeating.

| # | finding | evidence | confidence | changes priorities? |
|---|---|---|---|---|
| N1 | **Price-transform signals have no edge on this universe** — momentum, mean reversion, strong-trend, calm-trend | all four indistinguishable from 0.500; baseline n=66 | **high** | Yes — price transforms are closed as a family, not one at a time |
| N2 | **8-K/6-K event drift does not exist at a detectable magnitude** | 0.4912 at n_eff **400** independent windows | **high** — best-powered result in the project | Yes — the strongest negative available; event-drift is closed |
| N3 | **Periodic-report drift does not exist** | 0.5019 at n_eff 49 over 10 years | medium-high | Yes |
| N4 | **Slow-mechanism hypotheses are unmeasurable with reachable data** — insider buying, activist stakes, proxy drift | n_eff 1, 3 and 10 respectively; design effect up to **4352×** | high | Yes — stop proposing them until data depth changes |

## Validated positive results

| # | finding | evidence | confidence |
|---|---|---|---|
| P1 | **Industry evidence causally changes decisions** | ablation: 2 of 2 positions flip to WATCH when removed; 0 spurious | medium — n=2, live path only |

Nothing else. **No signal has beaten the baseline.**

## Integrity failures discovered

Each was found by measurement and would have silently corrupted results.

| # | failure | how it was caught | status |
|---|---|---|---|
| I1 | Evidence dated to *retrieval* time, not decision time — leaked future information into every historical replay | pre-commit suite | fixed; 2 regressions |
| I2 | Three tests were passing **because of** I1 | the fix broke them | fixed |
| I3 | Stale hardcoded `as_of` in the operating harness | the I1 guard stripped a whole cycle's evidence | fixed |
| I4 | Correlated observations counted as independent — manufactured an apparent 0.359 signal | clustering analysis | fixed; n_eff now computed always |
| I5 | Funnel modelled a branch as a chain — `no_trade: 833%` | building the report | fixed |
| I6 | Funnel stage exceeded its predecessor — `independent_evidence: 104%` | same | fixed |
| I7 | Own fix to I6 zeroed the terminals | same | fixed |

## Measurement techniques adopted

| # | technique | what it prevents |
|---|---|---|
| M1 | **Effective sample size (n_eff)** over merged time windows | counting correlated observations as independent |
| M2 | **Design effect** reported alongside every rate | error bars that are silently 20× too narrow |
| M3 | **Pre-registration** with all ten fields before any test | choosing the hypothesis after seeing the answer |
| M4 | **Ablation** as the standard for capability claims | crediting a component that changed nothing |
| M5 | **Metric-integrity test** — "could this move by editing a constant?" | Goodharting the objective |
| M6 | **Confidence over calendar time** for promotion | ranking from a sample too small to rank on |
| M7 | **Independence and relevance as separate conditions** | accepting corroboration that cannot speak to the claim |

## Engineering prediction accuracy

**7 predictions, 1 correct.** Four wrong bottleneck, one wrong scope, one wrong
direction. The one correct prediction (cycle 3, LV 0 → 1–3, landed at 1) is
also the only one that named a number in advance.

**This is itself a research asset**: intuition about this system's bottlenecks
has a measured 14% hit rate, which is the strongest available argument for
measuring before building.

## Knowledge that changes future priorities

1. **Event frequency is the enemy of independence.** Denser events merge time
   windows rather than adding them — more data made n_eff *smaller*. Any future
   data-acquisition proposal must be evaluated on independent windows, never
   on row count.
2. **The honest horizon and the powerful horizon coincide for fast mechanisms
   and diverge for slow ones.** Slow mechanisms are not under-powered by
   accident; they are unmeasurable at reachable data depth.
3. **Fixtures are insufficient for ranking.** They gave 45% strategic-reading
   yield against reality's 19% and inverted a ranking. Valid for regression,
   never for prioritisation.
4. **Corroboration is two conditions, not one.** Independence is about
   authorship; relevance is about the claim. Conflating them both excludes
   valid evidence and admits irrelevant evidence.
