<!-- DRAFT — approval queue item. Not published. Publishing requires per-item founder approval + PUBLISHING_ENABLED (publer_pipeline.py). -->
Weekly structural regime read, 2026-07-17.

Structural mechanisms matched this week: NONE MATCHED. That doesn't mean nothing is happening — it means the available evidence doesn't justify claiming a known historical pattern, so we say so instead of forcing a story.

3 of 5 indicator series were unavailable this run — they're labeled UNAVAILABLE, not papered over.

3 resolvable prediction(s) went on the append-only ledger, e.g.:

"P=0.72 by 2026-10-16: 10-Year minus 2-Year Treasury yield spread remains above +0.30 percentage points (consistent with a non-inverted, moderately steep curve regime)."

Every probability here is on an append-only ledger, graded by code against real data on its resolve-by date. Nothing has resolved yet, so no accuracy is claimed — publishing a prediction is not a claim of accuracy.

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
