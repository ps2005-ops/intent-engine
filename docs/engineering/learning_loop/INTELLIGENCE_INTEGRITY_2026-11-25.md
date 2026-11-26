# Intelligence integrity: results (2026-11-25)

Status labels used below:

* **IMPL**: implemented and tested.
* **OPER**: running in production on its own.
* **PROM**: experimentally promising, on held-out data.
* **HIST**: historically validated.
* **PROSP**: prospectively validated.
* **COMM**: commercially validated.

Every number links to an artifact in `reports/learning_loop/`. **Nothing is
PROSP or COMM.**

## 1. Scheduled production cycles

See §14, filled after the 19:15 learning run and the 20:30 night cycle.

## 2. Weekly regime report (OPER, replacing the LLM job)

* **Replacement.** `scripts/weekly_regime_report_deterministic.py` runs from
  the Monday 08:00 cron, pinned at `~/ie-learning-runtime`. The old line is
  commented with its original text, the crontab before and after is saved,
  and old reports are kept.
* **Isolation test.** Run in a minimal cron-like environment: rc 0. A
  2022-10-03 control reproduces the 2022 regime (tightening +2.48pp,
  inversion, 8.25% CPI).
* **What it cannot say.** No forecasts and no causal claims. Every label is
  printed with its value, threshold and margin. Today's two labels are both
  BORDERLINE (CPI 4.08% against 4%; unemployment −0.30pp against −0.30).
* **Defect found (not fixed; it needs a protocol amendment).** In the
  forward macro snapshot DFF is daily, but `econ/regime.classify` counts
  12 periods as a year. Policy tightening and easing can never fire on
  forward data, so the paper models' regime dummies are defined differently
  in training (monthly panel) and in registration. That is train/serve skew.

## 3. Evidence integrity

### 3a. Reader evaluation (PROM)

Two held-out samples were labelled from the text alone before scoring
(`reader_eval/`). Single annotator; 19 ambiguous items are listed for human
review.

| | Sample 1 (n=90 clear): v1 | Sample 1: v2.0 | Sample 2 (n=61 clear, fresh): v1 | **Sample 2: v2.1 (frozen)** |
|---|---|---|---|---|
| Accuracy | 0.79 | 0.84 | 0.57 | **0.89** |
| Demand-claim precision | 0.56 | 0.77 | 0.35 | **0.73** |
| False demand claims | 12 | 3 | 22 | **4** |
| Demand recall | 0.88 | 0.65 | 0.80 | **0.87** |
| Surprises identified | 4/10 | 3/10 | 3/9 | **8/9** |
| Asserted on ambiguous items | 7/10 | 0/10 | 9/9 | 4/9 |

* **How v2.1 was produced.** It was frozen after the sample-1 failures:
  a bare "top" read as beating estimates, and DAU or items-per-buyer were
  missing from the vocabulary. It was then scored once on sample 2.
* **Remaining failure: attribution.** Customer case studies and earnings
  previews are read as the subject's own demand.

### 3b. Attribution audit (1,460 evidence records)

| Defect class | Records |
|---|---|
| Price or valuation only | 83 |
| Analyst actions on other companies filed under JPMorgan | 25 |
| Customer case studies filed as the vendor's results | 11 |
| Stale historical-table rows (e.g. 2017 TCJA) | 8 |
| Name collisions (All-Link Air & Sea → Sea Ltd) | 2 |

## 4. Expectation grades (IMPL; corrections PROPOSED)

`expectation_grade_audit_2026-11-25.json`:

* **Same event, not later evidence:** 33 of 47 grades used an article about
  the same event as the basis. Matched by reporting period ("Q2 2026") or by
  a gap under 45 days.
* **Valid:** 14, of which 7 confirmed.
  * demand_strengthening 5/8
  * demand_weakening 2/5
  * pricing_power 0/1
* **Effect on the reported rate.** Valid grades confirm at 0.50, against the
  0.60 the runtime reports.
* **The invalid 33:**
  * 24 have later-period candidates needing review;
  * 9 await the next report.
* **Proposed correction.** 33 append-only invalidation events are in
  `PROPOSED_grade_invalidations.jsonl`. Not written; awaiting approval.

## 5. Learning degradation, root cause

* **Per-run yield is flat** (accepted per research run: 10.5, 7.8, 8.4, 8.0,
  10.2, 10.7, 12.7, 10.2 by half-month).
* **The 147 → 56/day fall** combines two things:
  * an inflated comparison window: early August ingested a backlog, with
    retrieved exceeding attempted and doubled cycles;
  * cycles lost to host sleep: 27–29 per half-month fell to 13–17.
    `caffeinate` now holds the host awake.
* **Source health** is mostly HEALTHY. Statistics Canada shows one
  AUTH_EXPIRED and one PARSER_BROKEN.
* **The 129 untested beliefs** are all still inside their evaluation
  windows (median close 2027-05-10). Most are slow structural families. This
  is time, not a resolver failure.

## 6. Mathematical activation traces

### Bayesian inference (IMPL; OPER after the runtime upgrade)

* **Root cause.** The estimator receives no behavioural evidence. BLS
  refuses the keyless runtime ("daily threshold … registration key ''"), so
  0 readings means the `bayes.update` loop never runs.
* **Fix.** A fallback to the FRED mirrors JTSQUR and CIVPART, with ALFRED
  first-release dates, used only when BLS refuses.
* **Trace after the fix:** 48 nodes, then `precision`×48, `_classify`,
  `update`, `apply`, giving 1 informative update into the
  `collective_state` publish step.
* **Second defect.** 24 monthly readings were counted as independent
  evidence about today (uncertainty 0.020, confidence 0.959). Now one
  reading is kept per series per cycle: uncertainty 0.10.
* **Still a limitation.** The quits → "perceived_control" construct is an
  untested CANDIDATE, and participation maps to no dimension.

### Other mechanisms

| Mechanism | State |
|---|---|
| Regime | Connected to the weekly report (§2). Regime features remain negative in the replay |
| Transmission, business graph, strategic interaction | Not activated. FX3 and FX6 are registered as BLOCKED with reasons; no exposure map or working interaction detector exists to connect |
| Calibration | The 33 invalid grades are excluded in the audit. Feeding the corrected set into `learning_health` waits on approval of the invalidations |

## 7. Original-thesis experiments

`PREREGISTRATION_FORWARD_EXPERIMENTS_2026-11-25.md`:

* **FX1** (surprise), **FX2** (belief change), **FX4** (intent vs
  behaviour), **FX5** (resource commitment), **FX7** (combined).
* **BLOCKED:** FX3 (transmission) and FX6 (strategic reaction).
* **Holdout.** The 2021–2026 holdout is declared spent.

**FX4 (OPER from tonight).**

* Step 5 of the learning cycle.
* Its dry run found and fixed a backdating risk: it would have registered
  NET with an August cutoff although that quarter had been filed in
  November.
* Triggers before registration are refused.
* Reported revenue and acquisition-driven guidance do not trigger.
* Today: 19 clean historical triggers. One Canadian National raise
  appears 9 times by syndication and is collapsed to one event. 0 forward
  forecasts registered today.
* Coverage is US-GAAP filers only. Honda, ASML, Infosys, Sasol and CN file
  IFRS.

## 8. Historical evidence and prospective capture

* **SEC (XBRL, submissions):** point-in-time, used.
* **GDELT:** the raw archive is reachable but terabyte-scale; the DOC API is
  throttled from this host.
* **Consensus expectations:** historically unavailable; not invented.
* **Prospective capture:** continuing. Each evidence item carries
  `available_at`/`observed_at` separately from `seen_at`.

## 9. Instrument eligibility (IMPL; OPER after the runtime upgrade)

`market/instrument_registry.py`:

* **The rule.** INELIGIBLE needs an issuer deregistration (15-12B/G) filed
  by the decision AND no price near it. A delisting inside the window exits
  at the last tradable close; it is never dropped.
* **Why the stricter rule.** The naive Form 25 rule excluded NEE, PG and
  SHOP, all of which trade (SHOP's Form 25 was its NYSE → Nasdaq transfer).
* **Isolated upgrade cycle.** 41 not-yet-graded OLO records were classified
  INELIGIBLE automatically.
* **Proposed correction.** 104 corrections of the old UNRESOLVABLE events,
  each naming the state it corrects. Not written; awaiting approval.

## 10. Founder Intelligence dossiers (IMPL, applied locally)

19 demand-weakening beliefs were audited (`belief_corrections_2026-11-25.jsonl`):

| Verdict | Count |
|---|---|
| Contradicted by source | 5 |
| Unsupported | 8 |
| Stale | 2 |
| Incorrectly attributed | 1 |
| Supported with qualification | 2 |
| Inferred with uncertainty | 1 |

* **Withdrawn or qualified.** 16 withdrawn and 3 qualified, through an
  append-only sidecar the loader honours. Dossiers are untouched.
* **Shown on the page.** The claim was printed in the founder strategic
  block for 5 companies before (América Movil, J&J, MercadoLibre, Sasol,
  Vale) and 0 after.
* **Recommendations unchanged.** `strategic_intelligence/reasoning._build_thesis`
  does not read these beliefs, so no recommendation changed. The defect was
  displayed context.
* **Review.** A blind review package is in `enterprise_review/`: 5 pairs,
  rubric, separate key. It needs domain reviewers; no COMM claim.
