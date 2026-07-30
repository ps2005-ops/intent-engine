# Architectural debt

Not technical debt. **Deliberately incomplete implementations, deferred
capabilities, and accepted-but-unproven assumptions** — recorded so a
placeholder cannot quietly become permanent by being forgotten.

The register exists because this project keeps choosing the smallest correct
thing. That is right, and its failure mode is that "smallest" becomes
"permanent" through nothing more than nobody writing it down.

## Temporary placeholders

| # | Placeholder | Introduced | Why it is temporary | Replaced when |
|---|---|---|---|---|
| P1 | Belief revision uses a fixed ±0.05 step, not a Bayesian update | cycle 6 | The likelihoods a real update needs have not been measured; inventing them puts a precise number on a guess | ≥30 resolutions give a measured base rate |
| P2 | `BASELINE_PROBABILITY = 0.55` is a stated prior, not a measurement | cycle 3 | Momentum has no demonstrated edge on this universe | Resolved outcomes justify a different number, through the promotion wall |
| P3 | `_KIND_TO_SOURCE_CLASS` maps unknown kinds to `company_owned` | cycle 2 | Conservative default, but it silently under-credits genuine outside sources whose kind is unrecognised | Evidence kinds are enumerated at the source rather than inferred |
| P4 | Hypothesis ↔ signal is 1:1 | cycle 7 | Only one signal exists, so the distinction is currently free | A second signal tests the same hypothesis |

## Deferred capabilities

| # | Capability | Deferred at | Blocked on |
|---|---|---|---|
| D1 | Knowledge graph ("held 17× under high inflation, mid-cap SaaS") | cycle 6 | Hundreds of resolutions across ≥2 observed regimes |
| D2 | Execution quality | cycle 6 | Fills existing in the market decision path |
| D3 | Calibration quality | cycle 6 | `A-M5`: n≥30 plus a human calibration review |
| D4 | Theory-of-the-system framework | cycle 7 | Engineering/research balance rule — three consecutive process cycles already |

## Assumptions accepted but unproven

| # | Assumption | Why it is currently accepted | What would disprove it |
|---|---|---|---|
| A1 | Harmonic decay is the right novelty shape | Matches how repeated sampling of one hypothesis behaves | Measured marginal information from repeat tests decaying at a different rate |
| A2 | `MATERIAL_MOVE = 5%` separates a real miss from noise | Round number, chosen before any data | Observed distribution of forgone moves showing a different break |
| A3 | The six listed gates are all legitimate refusal reasons | Each was derived from a real measurement | A gate that fires often and always precedes a large forgone move |
| A4 | Strategic reading is a prerequisite for a position | The reasoner's ordering assumes it | Positions taken on market evidence alone calibrating as well or better |

## Placeholder lifetime

Every row above carries the cycle it was introduced. **P2 and P3 are the
oldest** (cycles 2–3) and are the two most likely to be mistaken for settled
design. Neither is.

## Standing rule

A placeholder that survives five cycles without its unblocking condition
getting closer is no longer a placeholder — it is the design, and must either
be justified as such or replaced.
