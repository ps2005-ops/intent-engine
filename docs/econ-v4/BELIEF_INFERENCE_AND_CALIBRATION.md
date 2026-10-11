# BELIEF_INFERENCE_AND_CALIBRATION

## The update rule is a constant, not an inference

32 belief updates on record. Methods: {'CALIBRATED_HEURISTIC': 32}.
Effective sample sizes observed: {1.0: 32}.

Distinct posterior deltas across every update:

| delta | count |
|---|---:|
| -0.080 | 9 |
| +0.060 | 23 |

Two values, applied unconditionally. The magnitude carries no information
about the strength, independence or quantity of the evidence that triggered
it, so `CALIBRATED_HEURISTIC` names a constant.

## No belief has been tested twice

131 beliefs hold; 32 distinct beliefs have ever
been updated; **0** have been updated more than once. Effective sample
size is therefore 1.0 on every update and no posterior ever compounds. This is
the structural reason cumulative learning cannot yet be demonstrated: the
lifecycle reaches BELIEF_UPDATED and stops.

## Schema trap worth recording

The `belief` row is the **formation snapshot** in an append-only ledger, so
`posterior == prior`, `history == []` and `last_validated == ""` on all
131 rows is correct rather than a defect. Revisions live in
`belief_update` rows keyed `at` / `prior` / `posterior`. Reading belief rows
alone makes a working engine look dead.

## Calibration, measured properly for the first time

The former `expectation_calibration` field was `confirmed / resolved` — a hit
rate. Separated in `market_learning_health.v2`:

- **Hit rate** (how often it was right): 0.719, n=32
- **Probabilistic calibration** (do the numbers mean anything):

- Brier score: 0.2138 vs climatology 0.2021 -> skill -0.0576 (**WORSE than climatology**)
- Log loss: 0.6196 vs climatology 0.5941 -> skill -0.0428
- Forecast range: 0.5641 .. 0.654 (sd 0.0189, 11 distinct values over 32 predictions)
- Discrimination: **MEASURED**
  _forecast probabilities vary enough for a reliability curve to mean something_

| forecast | n | observed | gap |
|---|---:|---:|---:|
| 0.5-0.6 | 24 | 0.667 | +0.082 |
| 0.6-0.7 | 8 | 0.875 | +0.254 |

### Reading

The engine's probabilities are **worse than climatology** — always predicting
the base rate scores better. Both reliability bins show positive gaps, so the
priors are systematically **under-confident**: it says ~0.59 where reality is
~0.70. That is a correctable bias, and it is invisible to a hit rate.
