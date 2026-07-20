<!-- DRAFT — approval queue item. Not published. Publishing requires per-item founder approval + PUBLISHING_ENABLED (publer_pipeline.py). -->
Subject: Your structural regime read, 2026-07-17

Here's the latest structural read. Nothing has been simplified or hidden — where the evidence is incomplete, the report says so.

Where the regime stands:

- **Yield curve (T10Y2Y)**: not inverted  [FRED T10Y2Y, 2026-07-16]
- **Credit spreads (HY OAS)**: UNAVAILABLE — no verified number this run, so no claim is made
- **Inflation trend (CPI YoY)**: UNAVAILABLE — no verified number this run, so no claim is made
- **Unemployment momentum**: UNAVAILABLE — no verified number this run, so no claim is made
- **Drawdown (SPY)**: -0.91% off recent high  [Tiingo, 2026-07-16]

Mechanisms:

**NONE MATCHED** — none of the documented mechanisms cleared their trigger conditions.

That doesn't mean "nothing is happening." It means the available evidence does not justify claiming a known historical pattern — so the system says so rather than forcing a story.

Claims we put on the record (graded by code, not by us):

- P=0.72 by 2026-10-16: 10-Year minus 2-Year Treasury yield spread remains above +0.30 percentage points (consistent with a non-inverted, moderately steep curve regime).
- P=0.58 by 2026-09-15: SPY rebounds to within +1.0% of its recent running high within the next 60 days (mild mean reversion from current -0.91% drawdown).
- P=0.65 by 2026-10-01: US unemployment rate remains below 5.0% through end of Q3 2026 (persistent tightness in labor market).

Every probability here is on an append-only ledger, graded by code against real data on its resolve-by date. Nothing has resolved yet, so no accuracy is claimed — publishing a prediction is not a claim of accuracy.

Reply with what was wrong or what surprised you — that feedback goes straight into the loop.

---

## Claim-trace table (T:1–T:6 — required on every asset; not for publication)

| Trace | Claim | Grounds (gate-passed capability / ledgered fact) |
|---|---|---|
| T:1 | extraction restraint, closed taxonomy | Task 3 reliability gate (5x3 protocol) + v2 rerun PASS 2026-07-18; closed TriggerCondition enum, schema-enforced |
| T:2 | "says so when none match" | deterministic matcher returns empty on no overlap (match_mechanisms, tested); "correct silence" bar in gate + T005 bar (b) |
| T:3 | documented library, named sources, deterministic match | mechanisms.json: every historical_instance carries a real citation; matcher is zero-LLM code |
| T:4 | UNAVAILABLE labels, loud DATA GAPS | regime_report rendering + 2026-07-18 gap-rule amendment (render_data_gaps_section), both tested |
| T:5 | append-only ledger, code-graded | prediction_ledger.py append-only convention; resolve_prediction computes Brier in code |
| T:6 | no accuracy claim, public-as-it-accumulates | A-M5 ≥30-resolved wall + founder calibration review; ledger 0 resolved (ledgered fact) |
