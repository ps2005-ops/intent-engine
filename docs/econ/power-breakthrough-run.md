# Power breakthrough run — what was measured, and what it settled

**Code SHA at start:** `050f6a8` on `v6/unified`
**Preregistration hashes:** V1 `4ae395b62fb60f85`, H2 `69c6732028a20679`,
V2 (H3–H6) `d1e266aa7acfc67f` — the last frozen *before* the monthly panel
produced a single number.
**Panel content hash:** `d6cbed966dd4ca55`

---

## 1. Reconciliation found two defects before anything new was built

The run opened by reproducing the frozen `GLOBAL_COLLECTIVE_HUMAN_STATE_V1`
result. It did not reproduce. Chasing that produced the two most consequential
findings of the run.

**The origin grid was a string pattern, not a grid.** `run_v2_experiment.py`
derived forecast origins as *every vintage date in the panel ending in `-15`*.
`BOGZ1FL153064486Q` is quarterly with a 75-day publication lag, so its release
dates land on the 15th of January, April, July and October — and all 229 of
them were read as forecast origins. The acquisition had planned 115. The fix
in the previous cycle had landed in `run_regime_experiment.py` and not here.

**The walled panel had been overwritten by a leaked one.** Two scripts wrote
`reports/panel/historical_panel.jsonl` under different rules.
`build_historical_panel.py` fetched every series at *today's* vintage and
stamped each observation with its *original* release date. For a series that
does not revise, that is correct. For one that does, it is the exact leak
`market/alfred.py` exists to prevent, and it is invisible:

```
PSAVERT 2008-06   vintage 2008-07-31   value 4.6   (the 2026 revision; first print 2.5)
INDPRO  2007-12   vintage 2008-01-21   value 102.4 (the 2026 revision; 2008-02-15 vintage 114.1)
```

Because the stamped release date *precedes* the first real grid vintage,
`latest_vintage_of` preferred the leaked cell at a majority of origins.
`build_historical_panel.py` now refuses to run; the panel was rebuilt from
cache with **0 network calls**, and V1 then reproduced exactly:
`base 0.22664, augmented 0.23612, delta −0.00948`.

---

## 2. The V1 interval correction says the opposite of what was expected

The previous cycle concluded that V1's stored interval was too narrow because
it came from a row bootstrap. Re-run on the same paired differences:

| estimator | interval | half-width |
|---|---|---|
| row bootstrap (stored) | [−0.02618, +0.00661] | 0.01640 |
| origin-clustered | [−0.02586, +0.00643] | 0.01615 |
| episode-aware | **UNDEFINED** — 1 contiguous block | — |

The within-origin correlation of the paired *differences* is **0.005**. The
ten rows from an origin share their features, but the amount by which the
augmented model beats the base model on each is nearly independent — so
clustering costs almost nothing *here*. It cost a great deal on the
`INFLATION_SHOCK` slice, which is why the estimator was still right to change.

Both records are in `reports/evaluation_registry.jsonl`. Nothing was rewritten.

A **third** record corrects the second: it had recorded `episodes = 1`, counted
by contiguity, which always returns 1 for consecutive origins. Against the
discovered phase map, V1's fifty origins cover **5**. That changes what this
run may claim — the episode gain is ×3.0, not ×15.

---

## 3. What the monthly panel and the deep history bought

| | V1 (quarterly, 1998–) | V2 DEEP (monthly, 1978–) |
|---|---|---|
| raw rows | 500 | 1430 |
| origins | 50 | 481 |
| effective origins | 35.0 | 127.2 |
| independent episodes | 5 | 15 |
| median MDE | 0.01615 | 0.00436 |

`rows ×2.86, effective ×3.63, episodes ×3.00, MDE down 73%` →
**INFORMATION_GAINED_EPISODES**.

The deep arm buys the episodes; the monthly grid mostly buys rows. Adjacent
monthly origins have a lag-1 autocorrelation of 0.58, so 481 origins are worth
127 independent ones. `power.py` reports all four numbers and has no method
that prints a row count alone.

**The behavioural block is the binding limit, not the origin grid.** Measured
earliest ALFRED vintages: INDPRO 1960, UNRATE 1961, HOUST 1961, CPIAUCSL 1973,
PCEC96 1980 — but the credit and JOLTS series have none before 2011–2012. The
deep arm therefore runs a *narrower* block (2 behavioural series), and is
reported as narrower.

---

## 4. Four hypotheses, none supported

| | MODERN | DEEP |
|---|---|---|
| H3 global monthly | INSUFFICIENT_POWER | INSUFFICIENT_POWER |
| H4 stress-conditional | INSUFFICIENT_POWER | INSUFFICIENT_POWER |
| H5 early warning | NOT_SUPPORTED | INSUFFICIENT_EPISODES |
| H6 transmission residual | NOT_SUPPORTED | NOT_SUPPORTED |

Point estimates are almost uniformly negative: on the deep arm the stressed
slice is −0.01596 and the calm control −0.00258, which is the *opposite* of
H4's prediction — the layer hurts more under stress.

Verdicts are decided on the **episode-aware** interval, not the clustered one.
On DEEP the clustered interval [−0.01245, −0.00374] excludes zero while the
episode-aware [−0.02444, +0.00619] does not. Reporting the clustered one would
have claimed a resolved negative effect that fifteen episodes do not support.

---

## 5. §10 nearly ended the run, and the reason was the harness

The first monthly run failed the baseline gate in both arms: the macro model
scored Brier 0.25734 against a constant's 0.24435, and no value of the L2
penalty fixed it (in-sample barely moved from 0.243 at any penalty while
out-of-sample degraded monotonically as it fell).

The model was not overfitting; it was **misspecified**. One logistic was being
fitted across ten families with base rates from 0.28 to 0.92 and no feature
distinguishing them. Fitted per family, the same block beats the per-family
constant on labour (0.1817 vs 0.2258 at 180d; 0.1233 vs 0.2466 at 360d) and on
industrial production at 360d.

The gate now runs per family and **3 of 10 pass on the deep arm**. The
augmented block is scored only on those, and the selection is made from
base-model performance alone, so it cannot select for the effect being tested.

---

## 6. The one replicated positive finding is not a predictive one

Consumer sentiment **leads** housing starts by 6–8 months and industrial
production by 7–8 months, in *both* arms, on vintage-walled data. The
employment ratio is coincident with everything, which is what a labour
statistic wearing a psychological name looks like.

That enters the world model as **OBSERVED**, not PREDICTIVE. Leading a series
is necessary for being an early driver of it and is not sufficient, and the
forecasting test on the same panel did not support the block.

---

## 7. What was refused

- **Founder Intelligence: REFUSED.** §24 is conditional and the condition was
  not met. The six-company test was not run, because running it would produce
  six differentiated-looking outputs from a layer that has not shown it knows
  anything.
- **12 world-model edges added, all OBSERVED. 8 refused.**
- **Calibration: PRE_CALIBRATION.** Zero resolved forward predictions of the 30
  required. Every number in this run is HISTORICAL OUT-OF-SAMPLE PERFORMANCE,
  and `run_v2_report.py` now passes its own text through
  `calibration.assert_no_unsupported_claim` — a guard that had been
  implemented, unit-tested, and never called by anything that ships.
- **6 REAL_FORWARD expectations opened**, BASE and AUGMENTED for each of the
  three replicated temporal-order mechanisms. Neither is ever overwritten.

---

## 8. Four false discoveries killed

1. `INFLATION_SHOCK +0.171` — 30 rows, 14 origins, one episode.
2. `CREDIT_STRESS +0.029` — did not survive contemporaneous classification.
3. Two mechanisms SUPPORTED on the MODERN transmission test — both were scored
   on families whose base model loses to a constant, and both vanished when
   §10's gate was applied there too.
4. "The stored V1 interval is too narrow" — measured, and it is not.

## 9. Break proofs: 13/13 CAUGHT

Four proofs initially reported NOT_CAUGHT because they disabled a guard and
then called the same guard — a tautology. Rewritten to mutate the **call
site** or the **producer**, they caught. Proof 12 could not find a call site
to mutate, and *that absence was the finding*.

Every proof carries a positive control: the same check must pass on clean
code, or the result is reported UNRELIABLE rather than CAUGHT.

## 10. Performance

Panel 46.5 MB (was 800 MB, uncompacted and leaked), loads in 0.82 s, 220 MB
peak RSS, history lookup p50 1.05 ms / p95 1.68 ms. Rerunning the acquisition
makes **0 network calls**.
