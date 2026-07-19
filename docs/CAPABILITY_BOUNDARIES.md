# Capability boundaries — what the system does and does not do today

*Decision-support memo, analysis only. No code, no build order, no
accuracy claims. Written to answer a direct founder question: for each
absent capability, what would it take, what gate does it hit, and does it
move accuracy BEFORE calibration data exists? The short answer to that
last question is **no, for all four** — the reason is the same every time
and is stated once here: **the system has 0 resolved ledger predictions.
Until the A-M5 gate (≥30 resolved per source + human calibration review)
is met, NOTHING can honestly claim to improve predictive accuracy, because
there is no measured accuracy to improve or compare against.** Adding
capability changes what the system can *do*; it cannot change what the
system can *honestly claim* until the ledger resolves.**

## What the system DOES today (the honest capability surface)

1. **Regime read** — deterministic macro/market indicators (curve, credit
   spreads, inflation, unemployment, drawdown) from real FRED/Tiingo data,
   with provenance and loud "unavailable"/data-gap honesty markers.
2. **Structural mechanism extraction** — a reliability-gated LLM call maps
   a situation to a closed taxonomy of trigger conditions, tested to stay
   silent on genuine ambiguity; matched deterministically against a
   citation-carrying library of documented historical mechanisms (20 live,
   growing via the historical-study track).
3. **Forward prediction ledger** — probabilistic claims recorded
   append-only, graded by code against real data on their resolve dates,
   with dumb baselines for comparison. **0 resolved to date.**
4. **Founder-readable reporting** — presentation-grade rendering of the
   above with the honesty markers as features.

That is the whole surface. Everything below is OUTSIDE it.

## (a) Strategy backtesting — HELD behind A-M3

- **Status**: designed, HELD (docs/BA_ACCELERATION_PROPOSAL.md §2), no
  code. A-M3 forbids evaluating the LLM by "paper trading in the past."
- **What amending would cost**: a written A-M3 amendment (the exact text
  is drafted in the proposal), plus a quarantined `backtest_ledger.db`
  track that structurally never mixes with live calibration, pre-registered
  episodes, strict publication-date information-hiding, and model-memory
  mitigations.
- **The risk**: model memory. The LLM was trained on history and may
  *remember* what followed a test date; a backtest can look skillful for
  the wrong reason. That is precisely why the design quarantines the track
  and why A-M3 exists.
- **Moves accuracy before calibration?** No. A backtest produces a
  *diagnostic lower-bound on pipeline mechanics*, explicitly not comparable
  1:1 with live calibration and explicitly barred from counting toward the
  Alpaca gate. It cannot substitute for real resolved predictions.

## (b) Technical / chart analysis — absent, philosophically distinct

- **Status**: absent. This is a different *kind* of engine — pattern
  recognition on price/volume series, not causal-structural reasoning.
- **What adding it would entail**: a separate signal module (price-pattern
  detectors, indicator computations) and a decision about whether its
  outputs even enter the same ledger.
- **Honest note on validity**: the predictive validity of technical
  analysis is genuinely contested in the literature — some patterns show
  weak statistical edges in some regimes, many do not survive
  out-of-sample testing, and practitioner and academic views diverge
  sharply. Adopting it would import that contested status; it should not
  be presented as settled.
- **Moves accuracy before calibration?** No — and doubly so: it neither
  has resolved ledger predictions nor a non-contested accuracy claim to
  stand on. Adding it before the ledger resolves would be adding an
  unproven engine to an unproven one.

## (c) Company / fundamental analysis — absent, new data required

- **Status**: absent. The system reads macro/market regime, not
  individual-company financials.
- **What it would entail**: new data sources (filings, earnings,
  balance-sheet feeds), a company-entity data model, and extraction logic
  for fundamentals — a substantial ingestion layer that does not exist.
  (Note: the causal-graph pillar's news/filings ingestion is itself
  LATER-gated per TOOLS.md — Crawl4AI/Firecrawl behind the graph-population
  gate — so even the data plumbing is gated.)
- **Moves accuracy before calibration?** No. It would broaden *coverage*
  (what the system can analyze), not demonstrate *accuracy* — and its own
  predictions would join the same unresolved ledger under the same wall.

## (d) Quant forecasting methods (TimesFM / Kronos) — LATER-gated

- **Status**: LATER per TOOLS.md — gate is "Part C-M baseline conditions
  met." These are learned time-series forecasting models.
- **What it would entail**: integrating an external forecasting model,
  deciding how its point/interval forecasts relate to the structural
  engine's claims, and — critically — NOT letting a black-box forecaster
  quietly become the product in place of the transparent-methodology
  differentiator.
- **Moves accuracy before calibration?** No. A forecasting model has its
  *own* calibration burden; bolting it on would create a second
  unvalidated predictor, not a validated one. It would still owe the same
  ≥30-resolved evidence before any accuracy claim.

## The through-line (for the decision)

All four are **coverage/method expansions, not accuracy proofs.** None can
be marketed or relied upon as improving prediction until the live ledger
resolves enough predictions to measure calibration (A-M5). Two of them
(a, d) additionally carry their own gates (A-M3 amendment; Part C-M / the
Alpaca-class evidence bar), and two (b, c) would import unproven or
contested engines. The disciplined sequence the current design implies:
**let the ledger resolve first (first resolutions ~late Aug 2026), review
calibration, THEN decide which of these is worth its gate** — rather than
widening capability into a system whose core claim is still unmeasured.

*No accuracy claim appears in this document; the only performance
statement is the repeated, load-bearing disclaimer that none can yet be
made.*
