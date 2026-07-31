# Research asset ledger

A **living scientific record**, not an activity log. What this project knows,
when it learned it, when it was last checked, and whether it is still believed.

A research asset is a finding that **changes what future work should do**. A
day that produces none is an operating day, not a research day, and both are
legitimate.

## Knowledge decay

> Previously accepted conclusions remain open to re-evaluation. When evidence
> contradicts an asset it transitions **Accepted → Under Review → Confirmed or
> Retired**. No historical conclusion is immutable.
>
> **Confidence belongs to evidence, not to age.**

This is the opposite failure to the one the project spent fifteen days
avoiding. Early on the risk was concluding too fast; after months of operation
the risk is treating old conclusions as settled because they are old. An asset
that has not been re-validated is not thereby stronger.

`Last validated` is therefore a required column. An asset whose last validation
is far behind the present is a candidate for review regardless of how confident
it once was.

---

## Cumulative ledger

| # | asset | class | confidence | first observed | last validated | still believed |
|---|---|---|---|---|---|---|
| N1 | Price-transform signals have no edge on this universe | negative | high | Day 1 | Day 15 | **yes** |
| N2 | 8-K/6-K event drift does not exist at detectable magnitude | negative | high (n_eff 400) | Day 4 | Day 15 | **yes** |
| N3 | Periodic-report drift does not exist | negative | medium-high | Day 4 | Day 15 | **yes** |
| N4 | Slow-mechanism hypotheses are unmeasurable at reachable data depth | negative | high | Day 4 | Day 15 | **yes** |
| P1 | Industry evidence causally unlocks decisions | positive | medium (n=2, ablation) | Day 10 | Day 12 | **yes** |
| M1 | Effective sample size, not row count | technique | high | Day 3 | Day 15 | **yes** |
| M2 | Event frequency is the enemy of independence | principle | high | Day 3 | Day 5 | **yes** |
| M3 | Fixtures are insufficient for ranking | principle | high | Day 8 | Day 8 | **yes** |
| M4 | Independence and relevance are separate conditions | architecture | high | Day 7 | Day 11 | **yes** |
| M5 | Authorship ≠ subject | architecture | high | Day 11 | Day 11 | **yes** |
| M6 | Calendar time is not evidence | measurement | high | Day 14 | Day 16 | **yes** |
| M7 | Horizons belong to mechanisms, never to power | principle | high | Day 4 | Day 4 | **yes** |
| M8 | Intuition about this system's bottlenecks is ~14% accurate | meta | medium (n=7) | Day 3 | Day 16 | **yes** |

**Assets under review: 0. Retired: 0.**

Two assets — M3 (Day 8) and M5, M7 — have not been re-validated since they were
first established. Flagged here rather than silently trusted.

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
