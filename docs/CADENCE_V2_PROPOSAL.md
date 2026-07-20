# Cadence v2 — widened forward-prediction surface — APPROVED & IMPLEMENTED

*Phase 1 of the densification plan. Founder approved all three numbers
exactly as proposed on 2026-07-19 (loop 8): (1) allowlist as §1, (2) daily
cap = 8, (3) ceiling = $7 unchanged. Implemented same loop in
`core/daily_prediction_policy.py` + `scripts/daily_market_predictions.py`
with tests (allowlist membership, cap enforcement at 8, per-bucket spread,
5-instrument extra-window rotation incl. full-pool coverage, ceiling
math); suite green, exit-checked, one commit. Implementation note: the
rotating extra became a 5-instrument daily WINDOW over the 29-entry
non-core pool (window start steps by 5; gcd(5,29)=1 ⇒ every instrument
visited every 29 days) — this is the "rotating-extra pool grows
accordingly" clause of §1 made concrete, keeping the run at ≤10 data
calls. Forward-only; deterministic allowlist + pydantic validation at
record time; no accuracy claims; grading unchanged. Original proposal
preserved below.*

## Current surface (cadence v1, live)

- Instruments: 7 Tiingo (SPY, QQQ, IWM, TLT, GLD, XLE, XLF) + 6 FRED
  (T10Y2Y, UNRATE, CPIAUCSL, BAMLH0A0HYM2, DGS10, VIXCLS).
- Cap: 5 predictions/day; ≤4 model + ≤6 data calls/run.
- Ceiling: $7/mo estimated ($0.02/model call over-estimate).
- Kept guards: mechanism rotation (6 families), horizon buckets
  {14,30,60,90} + 14d floor, max 2/bucket/day, anti-duplication vs
  unresolved live, baseline pairing (2/day, 60d).

## Proposed widening

### 1. Instrument allowlist — add sector/breadth coverage (deterministic, pydantic-validated)

Add Tiingo sector/breadth ETFs (SPDR sector family + a few breadth/vol):
**XLK, XLV, XLY, XLP, XLI, XLB, XLU, XLRE, XLC** (the remaining GICS
sectors beyond the current XLE/XLF), plus **DIA, MDY, EFA, EEM, HYG, LQD**
(broad/intl/credit-ETF breadth). Add FRED macro series: **DGS2, DGS30,
T10YIE (breakeven inflation), DTWEXBGS (dollar), DCOILWTICO (WTI),
DEXUSEU**. All remain a fixed allowlist; the drafting call may only emit
rules against it; anything else is rejected at record time exactly as
today (M5 pydantic pattern). This roughly triples instrument breadth
(13 → ~30) while staying fully deterministic.

Rotating-extra pool grows accordingly so each day still fetches a bounded
number of series (the ≤N data-call budget is preserved; see §3).

### 2. Daily cap — raise 5 → 8 (recommended), with the guards intact

- New `DAILY_CAP = 8`. Keeps mechanism rotation, {14,30,60,90} staggering,
  **max-per-bucket raised 2 → 2** (unchanged — with 4 buckets, 8/day is
  exactly 2 per bucket, so density spreads evenly by construction),
  anti-duplication, and baseline pairing all unchanged.
- Recommend 8, not 10: 8 fills the 4 horizon buckets at 2 each cleanly and
  keeps a single drafting call's output focused; 10 would force >2/bucket
  or a second drafting call. If you prefer 10, say so and I'll set
  max-per-bucket to accommodate.

### 3. Budget ceiling — the matching adjustment (your explicit approval needed)

At cap 8, still **one drafting + one extraction call per run** (the cap is
on predictions emitted, not calls), so model calls/run are unchanged
(≤4 incl. retry headroom). Data calls rise with breadth: propose **≤10
data calls/run** (core snapshot + a wider rotating set). Monthly estimate
stays model-call-driven:

- ~21 trading days × ≤4 model calls × $0.02 = **≤$1.68/mo** on the honest
  over-estimate — comfortably under even the *current* $7 ceiling.
- **Proposed ceiling: keep $7/mo** (no raise needed; breadth adds data
  calls, which are $0 on Tiingo/FRED free tiers, not model calls). The
  park-if-exceeded guard is unchanged. **If you'd rather I raise the
  ceiling for headroom, name the number; otherwise $7 stands and I need
  only your approval of cap=8 + allowlist.**

### 4. Explicitly unchanged (the quality gates)

Mechanism-family rotation, horizon staggering {14,30,60,90} + 14d floor,
anti-duplication guard, baseline pairing, correct-silence on no-signal
days, append-only ledger, A-M5 ≥30-resolved wall before any calibration
claim, park-if-exceeded. Nothing about grading or claims changes.

## What I need from you (three explicit approvals)

1. **Allowlist** as listed in §1 (or a trimmed set you prefer).
2. **Daily cap** = 8 (or 10 with the noted per-bucket change).
3. **Ceiling** = $7 unchanged (or a number you name).

On your approval I implement the policy change (constants + rotation
pool + tests: allowlist membership, cap enforcement at the new value,
per-bucket spread at 8, ceiling math) behind the same bars as cadence v1,
suite green with explicit exit-code check, one commit.

## Staged, not built

No code changed this loop. This doc is the proposal; the diff is
mechanical once you pick the three numbers. Nothing runs the widened
cadence until it's approved AND live (and live daily runs happen on the
Mac — the sandbox has no Anthropic egress).
