# V4: two lanes — a forward record that can judge itself, and a world model that changes an analysis

**From:** `e71f0637` on `v6/unified`
**Panel:** `1c1351b3c12ab651` — 34 series, 200,824 cells, 313 network calls.

The historical human-state programme is **FROZEN_CANDIDATE**. This run did not
try to make it win. It did two other things.

---

## Lane A — the forward record

Twelve expectations, six BASE/AUGMENTED pairs, none due before 2027-02. That
is not a reason to ship an unexercised resolver: the day the first one is due
is the worst day to discover the resolver is wrong, and fixing it afterwards
destroys the property that makes the record worth having.

**Built:** a six-state machine (`OPEN`, `ELIGIBLE_FOR_RESOLUTION`, `RESOLVED`,
`EXPIRED_UNRESOLVED`, `INVALIDATED_DATA`, `BLOCKED_EXTERNAL`), deterministic
resolution contracts with an explicit `FIRST_RELEASE` / `LATEST_REVISION`
policy, a forward sample-quality wall carrying five numbers, and a calibration
ladder whose thresholds are **fixed now, before a single resolution**:

| rung | resolved | origins | families | episodes | may report |
|---|---|---|---|---|---|
| PRE_CALIBRATION | — | — | — | — | counts only |
| EARLY_CALIBRATION | 10 | 4 | 2 | 1 | per-prediction outcomes |
| CALIBRATION_ESTABLISHING | 30 | 12 | 3 | 2 | descriptive scores beside the sample |
| CALIBRATED | 60 | 24 | 4 | 3 | calibration curves and a verdict |

**Proved:** a backdated rehearsal ledger — 36 expectations, all resolved,
ladder moved to EARLY_CALIBRATION, 18 pairs scored. Its probabilities are
fixed constants (0.55 / 0.60), not model output. It proves the machinery and
is never mixed into the real record.

The real twelve stay `OPEN` at `PRE_CALIBRATION`, gap to the next rung: 10
resolutions, 4 origins, 2 families.

The `FIRST_RELEASE` distinction is the forward twin of the leak that cost a
whole panel: a prediction about what the world would *print* is not answered
by a later revision, however much better an estimate of the truth it is.

---

## Lane B — the world model, and the test that means something

**Coverage:** 11 of 17 dimensions LIVE, 6 BLOCKED (commodities, fx, liquidity,
real rates, volatility, positioning) — ranked by decision impact, and kept in
the denominator so coverage cannot inflate by asking for less.

**Six typed relations, two multi-order paths**, each step persisted with its
lag, uncertainty, regime and falsifier. `policy_to_housing` runs three orders
(DFF → MORTGAGE30US → PERMIT → HOUST, 210 days, net −1).

**Four of six relations did not fire** and became causal bleeds — all recorded
`CANDIDATE_NOT_PROVEN`. Rates fell and mortgage rates rose; permits fell and
starts rose. Measured non-responses with candidate explanations, not causes.

**Ten companies, 21 distinct channels.** Walmart's channel is basket mix;
Visa's is ticket value and cross-border; JPMorgan's is net interest margin;
Caterpillar's is customer financing cost. Not one paragraph under ten names.

### The two numbers that look better than they are

`DecisionDelta` scored 10/10 at 6/6 fields — against a **constant placeholder**,
so every field differs by construction. That measures the placeholder.

The load-bearing test is state-versus-state: move the economic state from
2025-08-27 to 2026-08-27 and see whether the analysis moves with it.

> **6 of 10 drivers moved. 5 of 10 company analyses changed**, with direction
> flips on BAA10Y, T10Y3M and MORTGAGE30US.

Five *not* changing is the honest half: those companies' drivers didn't move.
The world model is read, not merely present.

Channel specificity of 1.0 measures that the **authored** channels are
distinct. It is a floor against a template, not evidence of derived reasoning
— stated at the point of use rather than left to be discovered.

---

## The two bounded historical gaps, both closed

**A — pre-2012 household credit.** Four candidates found with archives
reaching before 2012. None cleared the equivalence bar; the best, NPTLTL, has
crisis agreement 0.89 and a rank correlation of **+0.15**. No defensible
household-credit substitute exists in a keyless archive. Search stopped, as
instructed.

**B — housing baseline.** Adding MORTGAGE30US (never revised, from 1971) and
PERMIT did not make the macro block beat a constant at either horizon in
either arm — 0.2724 against 0.2525 at best. `HOUST` stays **BASELINE_INVALID**.
It was not tuned until it won.

---

## Guards

**14/14 break proofs caught**, each with a positive control. Five initially
failed and four were the same tautology as the previous two runs — mutate the
guard, then call the guard. Rewritten to mutate the **producer** (the lineage
walk, the status a Bleed emits, the horizon comparison in `state_of`) or the
**call site**. The fifth was an over-broad positive control: it refused
`sentiment` anywhere in the world-model output, when `sentiment` is a
legitimate *coverage dimension*. Scoped to the company **driver table**, which
is where a frozen construct would actually do harm.

The stagnation detector fired `DEGRADING` on its first run — correctly, on a
bug in my own call site that compared today's state with today's.

---

## What is now true

- `REAL_FORWARD_EVIDENCE_RUNNING` — 12 open, resolver proved, ladder frozen
- `ECONOMIC_STATE_LIVE` — 11 of 17 dimensions, blocked ones named
- `COMPANY_TRANSMISSION_PROVEN` — 21 channels, 5/10 analyses move with the state
- `NO_UNSUPPORTED_HUMAN_STATE_CLAIMS` — REFUSED, and break proof 6 guards the driver table
