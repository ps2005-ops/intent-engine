# Strengthened economic intelligence standard (pre-registered 2026-11-28, before scoring)

The ORIGINAL economics metric is preserved unchanged and reported first. It
reads the X-Ray's "Why this decision" reason and passes only
`EVIDENCE_LED` / `CLASS_PRIOR_REINFORCED_BY_EVIDENCE`. Its classifier checks
for "conditions reach this business" FIRST, so any decision moved by a
measured economic channel is graded `ECON_LED` = BOUNDED, whatever else
supports it. It therefore measures *whether the company's own wording chose
the decision*, not whether the economic reasoning is sound. That is why
Pegasystems, UiPath, Forrester, Tenable, Amplitude and Rapid7 sit at 9.5: each
decision is moved by the measured rate channel (`ECON_LED`).

This standard measures something different and is **not easier**: a measured
variable alone fails, and a company narrative alone fails.

## Criteria (read from the rendered X-Ray, the surface a reader sees)

| # | Criterion | Pass condition |
|---|---|---|
| E1 | Company-specific exposure | >= 1 exposure stated in the company's OWN material, quoted, with >= 2 distinct phrases (customer-domain exposures >= 4) |
| E2 | Measured channel | >= 1 such exposure is joined to a channel the run's economic state actually measures ("measured by this engine") |
| E3 | Connection to the decision | the decision reason names a measured channel, AND that channel is one an evidenced exposure joins (the economy reached the decision THROUGH the company's exposure, not by class default) |
| E4 | Mechanism completeness | every exposure states transmission, direction, horizon, the condition it requires, a falsifier and the missing data |
| E5 | Uncertainty honesty | no size is claimed (no percentage, coefficient, elasticity or probability in the exposure section); unmeasured channels are labelled unmeasured |

**PASS** = E1–E5 all hold. **BOUNDED** = E1, E4, E5 hold (a real, honest
exposure that no measured channel yet carries). **FAIL** = no exposure
evidenced, or E4/E5 violated.

## What it deliberately does not do

* It does not re-grade the original metric, and its results are never merged
  into the original score.
* It does not credit a class-level transmission sentence.
* It cannot be passed by wording: E2 and E3 read what the run measured.

## Instrument correction (recorded before the final scorecard)

E5 first scanned the whole exposure section, including the company's OWN quoted
sentences, and failed Rapid7 on its 10-K's "...at 18% of our revenue". A number
the company published is evidence, not a size this system claims; E5 now
excludes quoted company text. The criterion is unchanged in intent.
