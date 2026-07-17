# Market engine trace

Session: 2026-07-16/17. Executing `~/Downloads/market-engine-execution-plan.md`
(companion to `~/Downloads/overnight-execution-plan.md`, whose Part A protocol
applies in full per the plan's own header) directly in this session — full
project context already held, applied directly rather than delegated.

**Explicit session scope, per direct instruction**: SUPERVISED SETUP RUN.
Execute M1, M2, M3 only, then stop before M4 (the first task that spends
live MODEL calls) for human review. M4-M9 are correctly **NOT STARTED**
below — not parked (no bar failed), not skipped-dependency (nothing blocked
them) — simply out of this session's authorized scope by direct instruction.

Legend: **DONE** / **PARKED** / **NOT STARTED (out of session scope)**.

Starting branch: `main`, clean working tree throughout (verified before
every commit, per A7).

---

## Phase 0 — prerequisite check — **DONE**

- `FRED_API_KEY`: **present** in the environment (checked via
  `os.environ`/`load_dotenv()`, value never printed or logged).
- `TIINGO_API_KEY`: **present** in the environment (same check, same
  non-printing discipline). Not consumed this session — no task in scope
  (M1-M3) touches Tiingo; that's M6.
- `.env` gitignore status: **confirmed** via `git check-ignore -v .env`
  (matched `.gitignore:5:.env`) before any task that reads it, per A-M1.
  Had this failed, the plan's own instruction was to stop immediately —
  moot here since it passed.

Consequence: because `FRED_API_KEY` was present, M1's live smoke test ran
for real rather than skipping (see M1 below) — the DATA-call spend below
reflects genuine live FRED traffic, not a hand-seeded fallback.

## Task M1 — Macro data layer (FRED client) — **DONE**

- Bars: (a) mocked tests against saved fixture JSON (parse, cache
  round-trip, guard-raises on both a truncated/empty-observations fixture
  and a real NaN observation) — **PASS**, 12 tests
  (`tests/test_macro_data.py`). (b) one live smoke test, fetching 2 real
  series (DFF, UNRATE) and asserting shape only — **PASS**, ran for real
  (key present), not skipped. (c) full suite green — **PASS**, 481 passed
  / 2 skipped, same 5 pre-existing `test_simulator_e2e.py` API-credit
  failures, zero regressions. (d) zero key material in the diff — **PASS**,
  checked directly by grepping the staged diff for both real key values
  (0 hits each) before commit, plus a standing regex test guarding the
  module source itself.
- Spend: **4 DATA calls** (2 to capture real fixtures — `DFF` and
  `VIXCLS`, both real live-captured FRED responses, not hand-seeded — plus
  2 from the live smoke test itself), **0 MODEL calls**. Well under the
  ≤30 DATA budget.
- Commit: `510307b`.
- Design notes, stated rather than silently decided:
  - The NaN guard test uses `VIXCLS`'s own real `"."` observation on
    2024-01-01 (a market holiday) rather than a fabricated edge case —
    the fixture genuinely demonstrates the exact real-world condition the
    guard exists for.
  - "Short/truncated series" is implemented as an empty-observations
    guard (a real-shaped FRED response with `"observations": []`,
    representing a range with no data) — the most literal, deterministic
    reading of the bar's own wording; not a judgment call requiring a
    park.
  - `requests==2.32.5` pinned in `requirements.txt` — already an
    installed transitive dependency (via `anthropic`/`google-auth`), not
    a new package; same "declare what's already there" treatment
    PROGRESS.md records for `Pillow` in the image-verification work.
  - `data/cache/fred/` added to `.gitignore` (runtime cache, mirrors
    `data/*.db`'s treatment) — `tests/fixtures/fred/` (checked-in,
    curated) is a separate, intentionally-tracked directory.
- Adjacent discovery, found and fixed **before** M1 could be committed
  under A7's suite-green-before-every-commit rule, not part of M1's own
  scope: the full suite was red at session start —
  `tests/test_pick_next_task.py::test_parse_real_roadmap_file_has_the_
  expected_runnable_tasks` still hardcoded `T002` as `RUNNABLE`, stale
  since `ROADMAP.md` marked T002 `DONE` in the prior session's final
  commit (`f86ad68`) — the suite was never re-run after that commit. Fixed
  in its own separate commit (`ad6ceb7`), correctly NOT bundled into M1's
  commit. Process note, disclosed rather than smoothed over: this fix was
  initially bundled into the wrong commit twice by a staging mistake (a
  leftover `git add` from an earlier inspection step) — corrected both
  times with `git reset --soft` before either commit had any external
  visibility (no push, no shared history, local session only) and
  re-committed with the correct scope. No content was lost or altered;
  final state is exactly as this trace describes.

## Task M2 — Regime indicator engine — **DONE**

- Bars: (a) each of the 5 indicators (`curve_inversion`,
  `credit_spread_percentile`, `inflation_trend`, `unemployment_momentum`,
  `drawdown_state`) asserted against hand-derived values on small
  constructed windows, independently verified by direct calculation
  *before* being written into the tests — **PASS**, 18 tests
  (`tests/test_regime_engine.py`). Per A-M3, no fixture represents or is
  scored against a real historical crisis; every number is a plain
  synthetic sequence chosen only to make the arithmetic checkable. (b)
  `regime_snapshot()` on a fixture date returns a fully-populated dict
  with provenance on every present field, and the literal string
  `"unavailable"` (never a crash, never a silent default) for a missing
  series, a series with too little history for its indicator, and — the
  one FRED-only real gap — `drawdown_state` when no price series is
  supplied (none of M1's 8 FRED seed series is a genuine price feed;
  that's Tiingo/M6) — **PASS**, including an explicit no-lookahead test
  (a future-dated observation proven not to leak into a snapshot dated
  before it). (c) full suite green — **PASS**, 499 passed / 2 skipped,
  same 5 pre-existing failures, +18 from this task.
- Spend: **0 MODEL, 0 DATA** — every fixture is constructed directly in
  the test file, no live calls of any kind.
- Commit: `0212b78`.
- Design notes: `unemployment_momentum`'s trigger threshold
  (`SAHM_TRIGGER_THRESHOLD = 0.50`) is the real, externally-published Sahm
  Rule recession-signal threshold (Sahm, Hutchins Center, 2019; also the
  documented trigger on FRED's own `SAHMREALTIME` series) — cited, not
  invented, and not tuned against this project's own fixtures.
  `inflation_trend`'s 0.1pp "stable" tolerance band is a rounding/noise
  tolerance for a 3-way categorical output, not a threshold chosen to
  make any fixture read a particular way — no fixture in this task
  represents a real crisis, so there was nothing to tune toward.

## Task M3 — Financial-crisis mechanism set — **DONE**

- Bars: (a) 9 new mechanisms present (17 total with the original 8),
  schema-valid, every `well_documented`-tier instance carries a real
  citation URL (checked directly by the pre-existing, unchanged
  `test_well_documented_mechanisms_have_a_real_citation_string`, which
  iterates all mechanisms generically and so automatically covers the 9
  new ones) — **PASS**. (b) matcher tests: a constructed regime-flavored
  condition list (`interconnected_counterparty_exposure` +
  `curve_inverted`) correctly ranks `bank_run_maturity_mismatch` first; a
  condition no mechanism declares (`inflation_rising`) returns `[]`; Task
  2's own original matcher scenario re-run unchanged against the extended
  17-mechanism set, confirming ranking/overlap for a pre-existing
  mechanism is unaffected — **PASS**, 6 new tests plus the one pre-existing
  cardinality test updated from 8→17 (a real, expected consequence of the
  extension, not a regression — the original 8 IDs inside it are
  untouched). (c) full suite green — **PASS**, 505 passed / 2 skipped,
  same 5 pre-existing failures, +6 from this task.
- Spend: **10 web searches** (budget ≤15), **0 MODEL, 0 DATA**.
- Commit: `6c6e091`.
- The 9 new mechanisms, tier, and real citation:
  | mechanism_id | tier | historical instance(s) | primary source |
  |---|---|---|---|
  | `leverage_cycle_bust` | well_documented | US household leverage, 2008 | NBER w15283 / AER 2011 (Mian & Sufi) |
  | `margin_collateral_spiral` | well_documented | Archegos, 2021 | Wikipedia / CNBC |
  | `bank_run_maturity_mismatch` | well_documented | Silicon Valley Bank, 2023 | FDIC.gov |
  | `carry_trade_unwind` | well_documented | Yen carry-trade unwind, Aug 2024 | BIS Bulletin No. 90 |
  | `reflexive_bubble` | **plausible** | Dot-com bubble, 2000 | novelinvestor.com + Soros, *The Alchemy of Finance* (1987) |
  | `monetary_tightening_lag` | well_documented | Volcker/1981-82 recession | Federal Reserve History |
  | `sovereign_debt_doom_loop` | well_documented | Eurozone crisis, 2010-2012 | Minneapolis Fed |
  | `capex_overbuild` | well_documented | Panic of 1873 (railroads) **and** dot-com fiber overbuild (2002) — 2 instances | Federal Reserve History/Smithsonian; Richmond Fed |
  | `money_market_contagion` | well_documented | Reserve Primary Fund, 2008 | Wikipedia / NY Fed Liberty Street Economics |

  8 of 9 tiered `well_documented`, 1 (`reflexive_bubble`) tiered
  `plausible` — the found sources for that one are a finance blog and
  Soros's own book, not a primary/major-outlet citation, the same honest
  tiering the original 8 mechanisms already used (3 of those 8 are also
  `plausible` on identical grounds).
- Design notes, stated rather than silently decided:
  - The regime-taxonomy extension (5 new `TriggerCondition` terms:
    `curve_inverted`, `credit_spreads_elevated`, `inflation_rising`,
    `unemployment_momentum_triggered`, `drawdown_gt_20pct`) is
    **deliberately narrower** than the plan's own illustrative example
    list, which also named `rapid_tightening`. M2 never built a
    rate-of-change indicator for the fed funds rate, so a
    `rapid_tightening` term would have nothing real behind it to check —
    adding it would violate the taxonomy's own "machine-checkable"
    requirement. Read the plan's example list as illustrative (`"e.g."`),
    not literal/mandatory, and built only what M2's real output actually
    supports.
  - `capex_overbuild` deliberately does **not** cite an AI-datacenter
    historical instance, even though the plan names it as an example of
    the kind of episode this mechanism covers. That situation is still
    unresolved (ongoing as of this session) — citing an outcome for an
    ongoing episode would assert a result that doesn't exist yet,
    exactly what this project's citation discipline exists to prevent.
    Used 2 real, resolved instances instead (railroads 1873, dot-com
    fiber 2002).
  - `leverage_cycle_bust` (new) and the original `debt_fueled_capacity_race`/
    `credit_contagion` are related but kept distinct: the new mechanism is
    about collateral-value-driven borrowing amplifying an asset-price
    cycle (a Mian-Sufi-style household/asset mechanism), not
    multi-competitor capacity racing or interbank counterparty panic —
    checked for overlap before writing, not assumed distinct.

## Tasks M4-M9 — **NOT STARTED (out of session scope)**

Per direct instruction: M4 (the reliability gate, the first task that
spends live MODEL calls) and everything downstream (M5-M9) were not
attempted this session. Nothing about them was parked (no bar was run or
failed) and nothing was blocked (M4's stated dependencies, M2 and M3, are
both now real and DONE — M4 is ready to run whenever authorized). This is
a deliberate scope boundary, not a gap in readiness.

---

## Session totals

- **Commits**: 4 substantive (`510307b` M1, `0212b78` M2, `6c6e091` M3,
  plus `ad6ceb7` the pre-existing-regression fix that unblocked M1's
  commit under A7) — one task each, every message references its task ID
  (or states plainly why it doesn't, for the regression fix).
- **Spend**: 4 DATA calls (all M1; well under M1's ≤30 budget, M2/M3's own
  0-DATA budgets untouched), 10 web searches (all M3; under its ≤15
  budget), **0 MODEL calls** (M1-M3 collectively budget 0 MODEL calls, and
  none were spent — the plan's own "the ONE new LLM capability this phase
  needs" is M4, correctly untouched this session).
- **Test suite growth**: 468 → 505 passed (+37: 13 in M1, 18 in M2, 6 in
  M3; the pre-existing-regression fix moved 1 already-failing test to
  passing without changing the collected count), 2 skipped throughout
  (pre-existing, unrelated: missing Google Calendar credentials, Anthropic
  API credits unavailable for one live scrap-metal test), same 5
  pre-existing `test_simulator_e2e.py` failures throughout (external
  API-credit exhaustion, not code — never touched, never silenced).
- **Hard reminders, checked directly rather than assumed**: no new pip
  dependencies beyond `requests` (already installed transitively, now
  properly pinned — same treatment as `Pillow`'s prior pin); zero key
  material in any committed diff (grepped directly against both real key
  values before every M1-adjacent commit); no indicator or trigger
  tuned against historical crisis outcomes anywhere in M2 or M3 (every
  M2 test fixture is synthetic; every M2/M3 threshold that could read as
  "tuned" — the Sahm 0.50pp trigger, the inflation-trend tolerance band —
  is either a cited external constant or a definitional necessity with no
  crisis-outcome assertion anywhere near it); every mechanism citation is
  real (10 real web searches, checked one at a time) or would have been
  tiered "speculative" had none been found (none were — 8 well_documented,
  1 plausible, 0 speculative, exactly mirroring the original 8's honest
  ratio).

**Stopped here per explicit instruction in the first session.** M1-M3
reviewed and approved by the human, including the disclosed judgment
calls (narrower taxonomy, no AI-datacenter citation, the separate
regression-fix commit) — all confirmed correct. Second session below
continues with M4, M5, M6, M8 per direct instruction (M7, M9 explicitly
excluded — M7 is the next human gate).

---

# Session 2 — GATE + RESOLUTION LAYER (M4, M5, M6, M8)

Legend: **DONE** / **PARKED** / **NOT STARTED (out of session scope)**.

## Task M4 — Regime-extraction reliability gate — **PARKED**

**Verdict, stated plainly up front**: PARKED. Not a bar failure — the
task could not run at all. The very first live call (round 1, call 1/15)
failed with a definitive Anthropic API billing error before any real
distribution could be collected. 0 of 15 round-1 calls succeeded; 0/40
budget spent.

**Real error, verbatim**:
```
anthropic.BadRequestError: Error code: 400 - {'type': 'error', 'error':
{'type': 'invalid_request_error', 'message': 'Your credit balance is too
low to access the Anthropic API. Please go to Plans & Billing to upgrade
or purchase credits.'}, 'request_id': 'req_011Cd6zRLBvGzYRr3hLZsMVc'}
```
This is the same external billing condition already documented elsewhere
in this repo for `test_scrap_estimate_live.py` (PROGRESS.md's scrap-metal
checkpoint) — a confirmed account-level state, not new. Not a
429/5xx-style transient error (a clear billing-state 400), so no retry
was attempted: retrying a confirmed balance-exhaustion error would not
produce new information, only spend more of the (already-zero) budget on
an identical failure.

**Script built and committed regardless, complete and reviewed-shape**:
`scripts/regime_extraction_reliability_gate.py`, exactly the base-plan
Task 3 pattern (`scripts/mechanism_extraction_reliability_gate.py`),
adapted for regime-flavored input — isolated call, information-hiding
(bare taxonomy names only, all 16 terms: the 11 original Task-2
conditions plus the 5 Task-M3 regime terms; no mechanism names/library,
no added definitions, matching Task 3's own precedent exactly).

**"No interpretation," enforced deliberately in how the 3 cases were
built**: every number below is either a REAL output of M2's own pure
functions (`credit_spread_percentile`, `unemployment_momentum`,
`inflation_trend`, `drawdown_state`), with only the raw numeric field
rendered — never the derived boolean/label field (`triggered`, `trend`)
those same functions also return, which would have handed the model its
own answer — or, for the T10Y2Y curve spread, the raw signed number
itself (there is no separate boolean to strip for that one; the spread
value IS the raw fact). The taxonomy shown to the model is bare condition
NAMES only, no definitions, so `drawdown_gt_20pct` etc. must be
self-explanatory the same way `concentrated_supplier_base` was in Task 3.

**The 3 constructed cases, verbatim (exactly what was sent, for you to
judge whether "clear" was actually clear)**:

### `clear_stress` — designed for exactly ONE unambiguous condition (curve_inverted)
```
- 10-Year minus 2-Year Treasury yield spread (T10Y2Y): -1.45 percentage points as of 2026-06-30 (source: FRED, series T10Y2Y)
- ICE BofA US High Yield Option-Adjusted Spread (BAMLH0A0HYM2): currently ranks at the 60th percentile of its own trailing 10-year window as of 2024-08-01 (source: FRED, series BAMLH0A0HYM2)
- CPI year-over-year: averaged 2.80% over the last 3 months vs. 2.88% over the last 12 months (source: FRED, series CPIAUCSL)
- Unemployment rate: 3-month moving average currently equal to its own low over the prior 12 months (delta 0.00 percentage points) (source: FRED, series UNRATE)
- A broad equity price index is currently 4.17% below its own recent running high (source: a broad market price index)

Headlines:
- "Retailers report steady holiday-season sales, in line with analyst expectations."
```
Design rationale: after a first design pass with 5 simultaneously-clear
conditions was rejected as methodologically unsound (see "design notes"
below), this was narrowed to ONE dominant, extreme signal (a deeply
negative spread, -1.45pp) with every other number left deliberately
unremarkable — mirroring Task 3's own narrow "clear" cases (1-2
conditions, not 5). Expected stable answer: `{curve_inverted}` only.

### `clear_benign` — designed for the empty set
```
- 10-Year minus 2-Year Treasury yield spread (T10Y2Y): +1.35 percentage points as of 2026-06-30 (source: FRED, series T10Y2Y)
- ICE BofA US High Yield Option-Adjusted Spread (BAMLH0A0HYM2): currently ranks at the 15th percentile of its own trailing 10-year window (source: FRED, series BAMLH0A0HYM2)
- CPI year-over-year: averaged 2.10% over the last 3 months vs. 2.18% over the last 12 months (source: FRED, series CPIAUCSL)
- Unemployment rate: 3-month moving average currently 0.03 percentage points BELOW its own low over the prior 12 months (source: FRED, series UNRATE)
- A broad equity price index is currently at its own recent running high, 0.00% off (source: a broad market price index)

Headlines:
- "Consumer confidence index ticks up for a third consecutive month; economists describe underlying trends as steady."
```
Every number here is calm/normal or actively improving (the unemployment
delta is negative — the labor market cooling toward its own recent best,
not worsening). Expected stable answer: `{}` (empty), a genuine "nothing
here" case per the extraction prompt's own instruction to select FEW or
NONE rather than force a selection.

### `ambiguous` — designed to be borderline on every axis at once
```
- 10-Year minus 2-Year Treasury yield spread (T10Y2Y): -0.04 percentage points as of 2026-06-30 (source: FRED, series T10Y2Y)
- ICE BofA US High Yield Option-Adjusted Spread (BAMLH0A0HYM2): currently ranks at the 65th percentile of its own trailing 10-year window (source: FRED, series BAMLH0A0HYM2)
- CPI year-over-year: averaged 3.40% over the last 3 months vs. 3.18% over the last 12 months (source: FRED, series CPIAUCSL)
- Unemployment rate: 3-month moving average currently 0.20 percentage points above its own low over the prior 12 months (source: FRED, series UNRATE)
- A broad equity price index is currently 11.82% below its own recent running high (source: a broad market price index)

Headlines:
- "Manufacturing activity contracts for a third straight month, but services-sector growth remains resilient and consumer spending is holding up."
- "Fed officials are described as 'closely watching' incoming data but have given no signal of imminent policy action."
- "Analysts remain split on whether this represents an early warning sign or a temporary soft patch."
```
Every single number is deliberately borderline: the spread is
technically negative but by 4 basis points (noise-level, not a real
inversion); the credit-spread percentile is mid-high but not extreme;
the inflation uptick is modest; the unemployment delta (0.20pp) is real
but well short of a dramatic move; the drawdown (11.82%) is meaningful
but well under the 20% bar. The headlines explicitly state analysts are
split. No single number or headline was written to obviously "win."

**Bars, as written in the plan**:
- (a) ≥4/5 modal agreement on the two clear cases: **NOT EVALUATED** — 0
  successful calls.
- (b) ambiguous case must not be confidently unanimous: **NOT
  EVALUATED** — 0 successful calls.
- (c) real distributions in the TRACE: **N/A** — no distributions exist
  to record; the verbatim error above is the complete real result.

**Commit**: `9a0be6b`.
**Spend**: 0 MODEL calls succeeded (1 attempted, failed before any
response), 0 DATA calls.
**What a human should decide**: add Anthropic credits, then re-run
`python scripts/regime_extraction_reliability_gate.py` unchanged — no
code or case-design decision is pending, only the external billing
constraint. Per the plan's own scope wall, M4's verdict gates only M7's
extraction path (M7 may run matcher-only if M4 ultimately parks on its
actual bars) — it does not block M5, M6, or M8, none of which depend on
M4, and this session proceeded to them per direct instruction.
