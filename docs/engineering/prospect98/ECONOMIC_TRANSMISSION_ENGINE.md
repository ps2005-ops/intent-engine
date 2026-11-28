# Company economic transmission: architecture, channel registry, audit (2026-11-28)

## The chain, as executed (not as imported)

```
published economic state (market engine, econ/state_snapshot + nodes; read-only copy per round)
  -> measured kinds: treasury_10y, wages, labour, inflation, financing (+ quits, participation, fiscal)
external context of the run ──┐
  macro factors cited in retrieved documents -> _ECON_EXPOSURE_MAP -> kinds
company-authored retrieved documents ──┐
  executive/exposure_map.build(own text, business-model class)        [NEW]
     -> evidenced exposures (>=2 own phrases; customer-domain >=4; quoted sentence)
     -> econ_kinds(): wages | policy_rate | financial_conditions | fx_dxy | industrial_production
founder_economy.block(economy, exposures = cited kinds + evidenced kinds)   [JOIN EXTENDED]
  -> ids only where the kind is MEASURED in the published state ("US:MARKET_RATE", "US:LABOR")
analysis_selection._score_archetypes(..., facts.economic_ids)
  -> a measured channel moves the decision (+4) -> X-Ray "Why this decision"
webapp: X-Ray + full analysis render "How economic conditions reach <company>"
  (relationship, own sentence, transmission, consequence, assumption tested,
   direction, horizon, required condition, falsifier, missing internal data,
   measured / not measured by this engine)
```

Single definitions: kind->channel is `founder_economy.KIND_CHANNEL` (the
exposure map imports it); the business class is the run's canonical profile
inputs; the economy is read once per request.

## Measured-channel registry (what the published state actually carries)

| Kind | Channel | Source in the engine | Applies to (exposure) | Status |
|---|---|---|---|---|
| treasury_10y / real_yield | MARKET_RATE | econ nodes `treasury_10y` (208 observations in the round copy) | customer finance budgets; venture/SMB customer financing; class transmission | MEASURED |
| wages | LABOR | econ nodes `wages` (136) | delivery labour (services firms) | MEASURED |
| labour | UNEMPLOYMENT | econ nodes `labour` (132) | — (no company exposure maps to it yet) | MEASURED, unused |
| inflation | INFLATION | econ nodes `inflation` (132) | — | MEASURED, unused |
| fx_dxy | CURRENCY | not in the published state | international revenue | **NOT MEASURED** (missing economic data) |
| industrial_production | INDUSTRIAL_DEMAND | not in the published state | customer procurement / supply-chain budgets | **NOT MEASURED** (missing economic data) |
| cloud / compute spend | — | no series | usage-priced compute; hyperscaler channel | **NO CHANNEL** (missing channel) |
| public-sector budgets | — | `fiscal` nodes exist but no channel id | public-sector demand | **MISSING MAPPING** |
| compliance obligations | — | no series | compliance-driven demand | **NO CHANNEL** |

## Why only 8 companies met a measured channel (c2), classified

| Cause | Companies (round 8, 70) | Resolution |
|---|---|---|
| Missing company-to-channel mapping: the join saw only macro factors cited in retrieved documents | the main cause | **FIXED** (evidenced exposures join): 8 -> 18 |
| Missing economic data (FX, industrial production not published) | international-revenue and procurement-domain companies | open: needs an FX and an industrial-production series in the market engine (FRED DTWEXBGS / INDPRO are public) -- a market-runtime change, not made from the qualification branch |
| Missing channel (cloud spend, compliance) | usage-priced and compliance-driven companies | open: no public series of adequate frequency identified; labelled unmeasured |
| Missing mapping (fiscal -> public-sector demand) | 18 companies with public-sector exposure | open: `fiscal` nodes exist; a FISCAL channel would need a transmission entry and a decision mapping |
| Insufficient evidence (no exposure in the company's own material) | 26 | honest NO_EXPOSURE_EVIDENCED |
| Site refuses the reader (no own text) | Coupa, JAGGAER, Ivalua, Prophix, Drivetrain, BitSight, Sysdig, Domo | external |

## Mathematics: what is and is not used

The connection is a **deterministic, evidence-gated join** -- the simplest
mechanism that solves the problem. No coefficient, elasticity, lag or
probability is estimated: there is no company-level outcome series (private
companies publish no revenue) to estimate one from, and inventing one is
refused. Candidate methods evaluated and NOT activated:

| Method | Problem it would solve | Why not now |
|---|---|---|
| Distributed-lag / local projections | timing of a channel's effect on company revenue | needs a company outcome series; absent for 85 of 98 |
| Hierarchical Bayesian exposure | partial pooling of exposure strength across a category | needs observed outcomes per company to update on; would present a prior as a measurement |
| Partial identification | bounds on effect size | the bound would be the sector range, which is a class prior, not this company |
| Dynamic factor / state-space | the economy side | already exists in the market engine; consumed as published state |

These stay in shadow until an observation contract supplies company-level
outcomes (V4: authorised internal revenue by segment would make the
distributed-lag estimate identifiable).

## V3 / V4 / V5

* **V3 (operational):** the exposure map from public evidence, joined to the
  measured state, on the X-Ray and full analysis.
* **V4 (roadmap, not connected):** each exposure names the internal series that
  would size it ("usage per customer", "utilisation, bill rates", "revenue by
  billing currency"); the same exposure contract would take them.
* **V5 (roadmap):** a measured channel moving past an exposure's condition is
  the trigger for a bounded investigation and a human-approved decision.

## Validation status

Research knowledge, not validated predictive knowledge. No exposure is
confirmed because its variable moved; an observation contract would need the
company-specific consequence (e.g. bookings by buyer function) to be observed.
