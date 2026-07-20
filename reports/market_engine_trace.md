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

## Task M4 — Regime-extraction reliability gate — **DONE (PASS)**

**Verdict, stated plainly up front**: **PASS**. Bar (a) holds on both
clear cases (5/5 modal agreement, not just the required ≥4/5). Bar (b)
holds — the ambiguous case produced 4 distinct answers across 5 runs,
nowhere close to confident unanimity. 15/15 round-1 calls succeeded, no
round 2 needed. 15/40 budget spent.

**First blocked by a real, external billing condition, resolved before
this result — kept here as part of the real record, not edited out**:
the first attempt (previous session) failed on call 1/15 with a
definitive Anthropic credit-exhaustion error:
```
anthropic.BadRequestError: Error code: 400 - {'type': 'error', 'error':
{'type': 'invalid_request_error', 'message': 'Your credit balance is too
low to access the Anthropic API. Please go to Plans & Billing to upgrade
or purchase credits.'}, 'request_id': 'req_011Cd6zRLBvGzYRr3hLZsMVc'}
```
the same external condition already documented elsewhere in this repo
for `test_scrap_estimate_live.py`. After credits were added, a second
attempt still failed, but with a DIFFERENT, more specific error —
`401 authentication_error: "API key is invalid"` — indicating the
billing action had also rotated/invalidated the key then in `.env`. A
newly-generated key was pasted in by hand and still failed 401 (likely a
manual copy-paste error); re-copying via the console's own Copy button
(rather than manual selection) finally produced a working key
(confirmed only by byte-length change each time, never by printing the
value). None of this involved any code change to the script or the
case-design — it was purely an external credentials issue, now
resolved.

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

**Real round-1 results, verbatim (5 runs × 3 cases, 15 calls)**:
```
[clear_stress] run 1/5: ['curve_inverted']
[clear_stress] run 2/5: ['curve_inverted']
[clear_stress] run 3/5: ['curve_inverted']
[clear_stress] run 4/5: ['curve_inverted']
[clear_stress] run 5/5: ['curve_inverted']
[clear_benign] run 1/5: []
[clear_benign] run 2/5: []
[clear_benign] run 3/5: []
[clear_benign] run 4/5: []
[clear_benign] run 5/5: []
[ambiguous] run 1/5: ['inflation_rising']
[ambiguous] run 2/5: ['credit_spreads_elevated', 'curve_inverted', 'inflation_rising', 'unemployment_momentum_triggered']
[ambiguous] run 3/5: ['curve_inverted', 'inflation_rising']
[ambiguous] run 4/5: ['curve_inverted', 'inflation_rising', 'unemployment_momentum_triggered']
[ambiguous] run 5/5: ['curve_inverted', 'inflation_rising', 'unemployment_momentum_triggered']
```

**Summaries**:
- `clear_stress`: modal `('curve_inverted',)`, **5/5** — exactly the
  designed single-condition answer, every run, no noise at all.
- `clear_benign`: modal `()` (empty), **5/5** — the model correctly
  selected nothing on a case designed to support nothing, every run.
- `ambiguous`: modal `('curve_inverted', 'inflation_rising',
  'unemployment_momentum_triggered')`, **2/5** — 4 distinct answers
  across 5 runs (a 1-condition answer, a 4-condition answer, a
  2-condition answer, and the 2-run modal 3-condition answer). Every run
  included `inflation_rising` (the one number written to be modestly,
  not extremely, elevated) and every run treated the borderline
  `curve_inverted` (-0.04pp) inconsistently — 4 of 5 included it, 1
  didn't — exactly the kind of genuine, evidence-tracking disagreement
  the case was designed to surface, not random noise (no run ever
  invented a condition unconnected to the given numbers).

**Bars, as written in the plan**:
- (a) ≥4/5 modal agreement on the two clear cases: **PASS** — 5/5 on
  both `clear_stress` and `clear_benign`.
- (b) ambiguous case must not be confidently unanimous: **PASS** — modal
  count is 2/5, not 5/5; 4 distinct answers observed. No round 2
  (strengthened-instruction re-run) was needed.
- (c) real distributions in the TRACE: **PASS** — see above, the actual
  per-run outputs and modal summaries, not just a pass/fail label.

**Commit**: `9a0be6b` (script, built and committed while still parked)
— this run itself produced no code change, only a real result; the
script ran completely unmodified from that commit.
**Spend**: **15 MODEL calls** (round 1 only, budget ≤40, 2 rounds max),
**0 DATA calls**.
**Consequence for M7**: M4 PASSED, so M7 (when it runs, still gated on
separate human review of this result and the calibration-footer design)
may use the real extraction path, not just matcher-only.

## Task M5 — Market prediction schema (ledger extension) — **DONE**

- Bars: (a) mocked round-trip with a market prediction including rule
  validation, malformed rule raises — **PASS**, 9 new tests
  (`tests/test_prediction_ledger_m5.py`), covering both rule shapes
  (`PctChangeRule`, `LevelRule`), 4 distinct malformed-rule cases (missing
  field, unknown `type`, wrong value type, and an explicit "never
  persists" check that the ledger file doesn't even exist after a
  malformed call). (b) old ledger tests pass unchanged — **PASS**,
  13/13 original tests in `tests/test_prediction_ledger.py`, zero edits
  to that file. Migration is additive — **PASS**, verified directly
  against a hand-inserted row shaped exactly like the pre-M5 schema
  (missing the 5 new keys entirely, not just set to null), confirmed it
  still parses via `Prediction.model_validate_json()`/`_read_all()`.
  (c) full suite green — **PASS**, 514 passed / 2 skipped, same 5
  pre-existing failures, +9 from this task.
- Spend: **0 MODEL, 0 DATA** (pure schema/validation work).
- Commit: `45428e0`.
- Design notes: no SQL migration was needed at all — the `predictions`
  table already stores each row as one JSON blob
  (`_ensure_schema`/`_persist`, both untouched), so new `Optional`
  `Prediction` fields are free at the storage layer; only the pydantic
  model changed. `resolution_rule` uses a real discriminated union on
  `"type"` (not a loose `dict`), so malformed-rule rejection comes from
  pydantic's own validation at `Prediction(...)` construction time inside
  `record_prediction()` — no hand-written validation code, and no risk of
  a malformed rule silently validating as a generic all-optional shape.
  `direction` is left as free text (no closed enum) since the plan states
  no fixed vocabulary for it — consistent with Week 1's own precedent
  (free-text `revenue`/`growth_rate`) of not inventing a taxonomy the
  spec didn't ask for. `resolve_prediction()`/`brier_summary()` are
  completely untouched — M6 reuses the existing resolve function as-is,
  per the plan's own instruction.

## Task M6 — Resolution layer (Tiingo + FRED graders) — **DONE**

- Bars: (a) fixture-based grading tests — **PASS**, 16 tests
  (`tests/test_market_resolution.py`): a hit case (+3% touch against a
  ≥2% threshold), a miss case (never crosses +1.5% vs. the 2% bar), an
  explicit weekend-gap case (window end lands on 2024-01-06, a real
  Saturday — the touch only occurs on 2024-01-08, the forward-searched
  Monday; asserted both as a direct unit test on `_forward_search` and
  end-to-end through `resolve_pct_change_rule`), an unresolvable case
  (unknown symbol, no data) verified excluded from `brier_summary` via a
  real ledger round-trip, and a hand-computed Brier value (probability
  0.8, `happened` → `(0.8-1.0)² = 0.04`) re-derived through the full
  `resolve_market_prediction → resolve_prediction` path, not just
  asserted in isolation. (b) idempotency — **PASS**: running
  `resolve_due_predictions` twice against the same ledger resolves 1 the
  first time and genuinely **0** the second (not just "same counts") —
  confirms the no-op is real, not coincidental. (c) live smoke — **PASS**,
  2 real Tiingo calls (real SPY price shape; a real end-to-end
  `resolve_pct_change_rule` call against real January 2024 SPY data,
  deliberately using a near-certain 0.01% threshold so the test proves
  the *wiring* works, not a market-timing claim) — ran for real since
  `TIINGO_API_KEY` is present, not skipped. (d) full suite green —
  **PASS**, 532 passed / 2 skipped, same 5 pre-existing failures, +18
  from this task.
- Spend: **3 DATA calls** (1 to discover Tiingo's real response shape
  before writing the parser, 2 from the live test file), **0 MODEL**.
  Well under the ≤10 DATA budget.
- Commit: `6b7242c`.
- Design notes, stated rather than silently decided:
  - **Touched-vs-closed**, concretely: pct_change rules with an ordering
    op (`>=`, `>`, `<=`, `<`) use TOUCHED semantics — the claim resolves
    `happened` the moment *any* trading day within the window crosses the
    threshold, matching how a claim like "SPY rises 2%+ within 60 days"
    actually reads in plain language (it doesn't require the price to
    *still* be up 2% on day 60 specifically). `==` uses CLOSED semantics
    — the window-end value specifically, the one case where an exact
    value at a specific point is the only sensible reading. This wasn't
    specified field-by-field in M5's schema (no separate touched/closed
    flag exists), so it's an implementation decision inside M6's grading
    logic, made explicit here rather than silently baked in.
  - Forward-search is used at 3 distinct points, not just the one the
    bar names: baseline-price lookup (if `created_at`'s date itself lands
    on a gap), the touched-window's effective end boundary (so a window
    computed to end on a weekend still correctly extends through the
    next real trading day rather than silently truncating one day early),
    and a level rule's `by` date. Capped at 10 calendar days for daily
    Tiingo data, 40 for monthly FRED data (a monthly series' real release
    gap is much wider than a long weekend) — past the cap, a source is
    treated as genuinely missing (`unresolvable`), never searched
    forever.
  - `list_predictions()` is a new, small, additive read primitive added
    to `prediction_ledger.py` in this task's own commit (not reopening
    M5's) — the resolve script needs "all due, unresolved predictions"
    and nothing exposed that before (only aggregate stats via
    `brier_summary`). Zero changes to any existing function in that file.
  - The resolve script filters to predictions with a non-null
    `resolution_rule` (rather than hardcoding `source in
    ("market","baseline")`) — correctly, automatically leaves
    premortem/scrap/digest/manual predictions alone (they never carry a
    rule) without needing to enumerate sources by name, and stays correct
    if a future source also adopts `resolution_rule`.

## Task M8 — Baseline predictors — **DONE**

- Bars: (a) mocked tests, both rules produce valid ledger rows with valid
  `resolution_rule`s — **PASS**, 9 tests
  (`tests/test_record_baselines.py`); determinism (same inputs →
  identical probability and `resolution_rule` content across two
  separate calls, `id`/`created_at` correctly differing since the ledger
  stamps those fresh by design) — **PASS**. (b) frozen constant's
  derivation documented in a comment with the data window used —
  **PASS**, see `BASE_RATE_SPY_2PCT_60D`'s own comment in
  `scripts/record_baselines.py`. (c) full suite green — **PASS**, 541
  passed / 2 skipped, same 5 pre-existing failures, +9 from this task.
- Spend: **1 DATA call** (the one-time base-rate history fetch), **0
  MODEL**. Well under the ≤5 DATA budget.
- Commit: `5e0e30b`.
- **The real, one-time base-rate computation** (not asserted, actually
  run this session): SPY adjusted closes from Tiingo, 2021-01-01 through
  2026-07-16 (a single fetch, 1389 daily observations). For every trading
  day with a *complete* forward 60-calendar-day window available (1348
  such days — the final ~60 days of the series were excluded, since their
  true 60-day-forward outcome isn't knowable yet), checked whether the
  price touched ≥2% above that day's own price at any point in the
  following 60 days — deliberately the exact same touched-semantics
  evaluation `core.market_resolution.resolve_pct_change_rule` uses for a
  real claim of this shape (not a separate ad hoc definition, for direct
  comparability against what the ledger will actually grade). **Result:
  1089 of 1348 windows (80.79%) touched the threshold** →
  `BASE_RATE_SPY_2PCT_60D = 0.8079`, frozen. Recomputing this later is a
  deliberate, separate decision this script never makes automatically.
- Design notes: both baseline rules share one `resolution_rule` shape
  (`pct_change`, `SPY`, `>=0.02`, `60 days`) and flow through the exact
  same M6 resolution path and M5/ledger Brier scoring as any other market
  prediction — no special-cased handling anywhere downstream, which is
  the entire point of a baseline (it has to be graded the same way the
  real thing will be, or the comparison means nothing). A guard in
  `record_base_rate_baseline` (implicit via its fixed `INSTRUMENT`/
  `THRESHOLD`/`WINDOW_DAYS` module constants, not a runtime check) keeps
  the frozen constant tied to exactly the claim shape it was computed
  for — the momentum rule and base-rate rule are not parameterized to
  drift apart from what was actually measured.

---

# Session 2 totals

- **Commits**: 8 substantive task commits (`9a0be6b` M4-parked,
  `45428e0` M5, `6b7242c` M6, `5e0e30b` M8) plus 4 trace-append commits
  (`53ac5f5`, `61d32eb`, `8a1fb99`, and this file's own upcoming commit
  for M8) — one code commit per task, one trace commit per task, per
  direct instruction this session.
- **Spend**: M4 — 0 successful MODEL calls (1 attempted, failed on a
  confirmed credit-exhaustion error before any response); M5 — 0 MODEL,
  0 DATA; M6 — 3 DATA, 0 MODEL; M8 — 1 DATA, 0 MODEL. **Total this
  session: 4 real DATA calls, 0 successful MODEL calls, 0 web searches.**
- **Test suite growth**: 505 → 541 passed (+36: 0 net from M4 [parked
  before any test could be written against a real result], 9 in M5, 18
  in M6, 9 in M8), 2 skipped throughout (same pre-existing, unrelated
  causes), same 5 pre-existing `test_simulator_e2e.py` failures
  throughout (external API-credit exhaustion — the SAME root cause M4
  hit live and directly confirmed this session, not a new or different
  problem).
- **M4's real, unresolved blocker**: Anthropic API credits are exhausted
  account-wide as of this session — this affects M4 specifically (it
  needs live MODEL calls) and is the same condition already responsible
  for the 5 standing `test_simulator_e2e.py` failures. Nothing else in
  this session needed a MODEL call, so M5/M6/M8 were unaffected. **What a
  human should decide**: whether/when to add credits; M4's script needs
  no further changes, only a re-run once credits exist.
- **M7, M9**: correctly **NOT STARTED**, per direct instruction — M7 is
  the next human gate (review M4's distributions, once they exist, and
  the calibration-footer design) before it runs; M9 documents the whole
  phase and depends on all prior tasks including M7.

**Stopped here at the time.** M4 needed Anthropic credits before it
could produce a real verdict; M7 and M9 remained explicitly gated on
human review.

---

# Session 2 addendum — M4 re-run to a real verdict

Credits were added; the first re-run still failed (401, "API key is
invalid" — the billing action had rotated the key); a hand-pasted new
key also failed 401 (likely a manual copy-paste error); a key re-copied
via the console's own Copy button finally worked. No code or case-design
change was made at any point in this sequence — see M4's own entry above
(now updated in place) for the full real error sequence and the actual
passing result.

**M4 final verdict: DONE (PASS)**, no code changes, script unmodified
from commit `9a0be6b`. Updated totals:

- **Spend (M4 only, this re-run)**: 15 MODEL calls (round 1, no round 2
  needed), 0 DATA. Session 2's running total across all 4 tasks now
  stands at 4 DATA calls, **15 MODEL calls**, 0 web searches.
- **M7's extraction-path gate is now resolved**: M4 passed, so a future
  M7 run may use the real regime-extraction path rather than falling
  back to matcher-only. M7 itself is still not started — the human gate
  is on reviewing this result and the calibration-footer design, per
  standing instruction, not on M4's verdict alone.
- M9 remains correctly not started (depends on M7).

**Stopping here.** M4 is now a real, passing result. M7 and M9 remain
explicitly gated on your review.

---

# Session 3 — M7 (extraction path authorized) + M8 run + M9 + operational handoff

M4 reviewed and approved by the human: the ambiguous-case distribution
(2/5 modal, 4 distinct answers) is exactly the honest-uncertainty
behavior the gate exists to verify. **Extraction path authorized for
M7.**

## Status check — M5, M6, M8 (previous session's scope)

Per direct instruction, verified explicitly before anything else in this
session, not assumed from memory:

- **M5 — Market prediction schema — DONE.** Commit `45428e0`, verified
  present on `main` (`git show --stat 45428e0`). Bars, as recorded in
  Session 2 above: (a) mocked round-trip + malformed-rule rejection —
  PASS, 9 tests; (b) 13/13 old ledger tests unchanged — PASS; migration
  additive, old rows verified readable — PASS; (c) suite green at the
  time, 514 passed / 2 skipped (+9), same 5 pre-existing failures.
- **M6 — Resolution layer — DONE.** Commit `6b7242c`, verified present.
  Bars: (a) fixture-based grading (hit/miss/weekend-gap/unresolvable) —
  PASS, 16 tests; (b) idempotency (second run genuinely 0) — PASS;
  (c) live smoke, 2 real Tiingo calls — PASS; (d) suite green, 532
  passed / 2 skipped (+18), same 5 pre-existing failures.
- **M8 — Baseline predictors — DONE (code).** Commit `5e0e30b`, verified
  present. Bars: (a) mocked tests, determinism — PASS, 9 tests; (b)
  frozen constant documented (`BASE_RATE_SPY_2PCT_60D = 0.8079`,
  derivation in-comment) — PASS; (c) suite green, 541 passed / 2 skipped
  (+9), same 5 pre-existing failures. **Code is DONE; the plan's own
  step 3 for this session — actually RUNNING `record_baselines.py` once,
  timed to right after M7's first real market predictions — is separate
  operational work, done later in this session, see below.**

All three verified against the CURRENT `main` (not re-derived from
memory), and the current full suite is green as of this session's start
(**547 passed, 1 skipped, 0 failed** — improved from the 505/2/5 state
recorded when M5-M8 were originally built, because the same credit/key
fix that unblocked M4 also fixed the 5 standing
`test_simulator_e2e.py` failures; nothing about M5/M6/M8 themselves
changed). **All three confirmed DONE — proceeding directly to M7, no
rework needed.**

## Task M7 — Weekly regime report — **DONE**

Real extraction path used throughout (M4 passed, authorized by the
human this session) — no matcher-only fallback needed.

**A real, significant finding hit mid-task, fixed within this task's own
budget, not glossed over**: the first live attempt crashed outright.
FRED marks market-holiday dates with `"."` for daily series (e.g.
Juneteenth, 2026-06-19, for `T10Y2Y`) — M1's hard NaN guard (already
reviewed and correct; untouched here) raises on ANY such value anywhere
in a fetched range. A 30-day `T10Y2Y` window and `BAMLH0A0HYM2`'s
structurally-required 10-year lookback are both near-certain to contain
at least one such gap. Fixed at the M7 fetch layer only: a per-series
fetch failure is now caught in `fetch_current_series_data` and that
series is simply OMITTED from `series_data` — reusing M2's own
already-tested `"series missing → unavailable"` path rather than
inventing a second resilience mechanism, and never silent (a `WARNING`
is printed naming which series and why). `T10Y2Y`'s window was also
narrowed 30d→10d (`curve_inversion` only ever reads the latest
observation, and 10 days safely clears the June 19 gap at zero extra
fetch cost) — this one specific, targeted, budget-neutral fix recovered
real `T10Y2Y` data on the next attempt. **`BAMLH0A0HYM2`/`CPIAUCSL`/
`UNRATE` remain structurally unable to shrink below their required
lookback and stayed `unavailable` in the final real run** — a real
architectural finding, not a bug I could cheaply route around: a
gap-tolerant recursive re-fetch was considered and rejected here, since
a series with dozens of calendar gaps across a 10-year window could cost
dozens of DATA calls against this task's ≤6 budget. **Flagged plainly
for your review, not silently patched**: whether M1's guard should gain
an opt-in "tolerate/skip individual gaps, report which dates were
skipped" mode is a real, separate design question — not decided here.

**The real, full rendered report** (the actual output of the real
end-to-end run, byte-for-byte, also saved at
`reports/weekly_regime_report_2026-07-17.txt`):
```
REGIME SNAPSHOT -- as of 2026-07-17
----------------------------------------------------------------------
Yield curve (T10Y2Y):        not inverted  [FRED T10Y2Y, 2026-07-16]
Credit spreads (HY OAS):     unavailable
Inflation trend (CPI YoY):   unavailable
Unemployment momentum:       unavailable
Drawdown (SPY):              -0.91% off recent high  [Tiingo, 2026-07-16]

Structural mechanisms possibly in play: none matched -- no forced match on an empty/weak signal.

RESOLVABLE PREDICTIONS RECORDED THIS RUN (source=market)
----------------------------------------------------------------------
- P=0.72 by 2026-10-16: 10-Year minus 2-Year Treasury yield spread remains above +0.30 percentage points (consistent with a non-inverted, moderately steep curve regime).
- P=0.58 by 2026-09-15: SPY rebounds to within +1.0% of its recent running high within the next 60 days (mild mean reversion from current -0.91% drawdown).
- P=0.65 by 2026-10-01: US unemployment rate remains below 5.0% through end of Q3 2026 (persistent tightness in labor market).

CALIBRATION (read-only; no feedback into generation)
----------------------------------------------------------------------
market: no resolutions yet.
baseline: no resolutions yet.
(The ledger accumulates from here -- per A-M5, no confidence adjustment happens until at least 30 resolved predictions per source exist.)
```

Real headlines fed into extraction (gathered via web search before this
task started, real and current, not fabricated): the June jobs report
miss (57K vs. ~110-115K consensus, unemployment steady at 4.3%),
futures pricing a possible October Fed rate hike, and a second
consecutive weekly bond selloff pushing yields to their highest since
mid-May. The model correctly used the headline's real unemployment
figure to ground its UNRATE prediction even though the `UNRATE` FRED
series itself was unavailable in the snapshot table that run — a real,
useful demonstration that the drafting call synthesizes numeric AND
headline evidence, not just one or the other.

**Bars**:
- (a) real end-to-end run on the current real snapshot, ≥1 genuinely
  matched mechanism OR correct silence — **PASS**: correct silence (the
  available signal — a non-inverted curve, a modest drawdown, mixed
  headlines — genuinely didn't clear any mechanism's trigger
  conditions; no match was forced).
- (b) recorded rows verified by direct DB read, sane probabilities,
  future `resolve_by`, valid rules — **PASS**. **5 real predictions
  total were recorded across this task's live debugging** (2 from the
  intermediate run before the `T10Y2Y` fetch fix — when `T10Y2Y`,
  `BAMLH0A0HYM2`, `CPIAUCSL`, and `UNRATE` were ALL unavailable, so those
  2 predictions grounded entirely in the drawdown number and headlines
  — plus the 3 shown above from the final run). None deleted — append-
  only per this project's standing convention (same discipline as every
  other ledger write in this codebase). Direct DB read confirmed all 5:
  probabilities `{0.65, 0.72, 0.72, 0.58, 0.65}`, all strictly in
  `(0,1)`; `resolve_by` `{2026-08-31, 2026-09-15, 2026-10-16, 2026-09-15,
  2026-10-01}`, all genuinely future relative to 2026-07-17; all 5
  `resolution_rule`s are valid, correctly-typed `PctChangeRule`/
  `LevelRule` instances (3 `pct_change`/SPY, 2 `level`/`T10Y2Y`+`UNRATE`).
- (c) language-wall grep bars — **PASS**, checked directly against the
  actual rendered file (not just the internal assertion): `grep -ic`
  for `"will happen"`, `"buy"`, `"sell"`, `"position size"` — **0 hits
  each**.
- (d) suite green — **PASS**, 562 passed / 1 skipped / 1 deselected (the
  confirmed-passing 10-minute live vision test, deselected only to avoid
  a redundant re-run, not because anything failed).

**Commit**: `01800d7`.
**Spend**: **6 DATA calls** (exactly at the ≤6 budget — `T10Y2Y` fetched
twice under two different windows during the live-debugging sequence
above, `BAMLH0A0HYM2`/`CPIAUCSL`/`UNRATE` once each, `SPY` once), **4
MODEL calls** (2 real end-to-end attempts × 1 extraction + 1 drafting
call each, well under ≤8), 0 additional web searches this task
(headlines gathered once, before the task started).

## Operational step — `record_baselines.py` run (per step 3, after M7)

Pure operational run, no code change — `scripts/record_baselines.py` was
already DONE (M8, previous session). Run once now, right after M7's real
market predictions, so the ledger's first cohort has engine and baseline
predictions sharing a horizon, per direct instruction ("the scoreboard
starts from the same date").

Real result: `record_momentum_baseline` → P=0.65 (SPY's real trailing
3-month return was positive), `record_base_rate_baseline` → P=0.8079
(the frozen constant). **Both landed on `resolve_by=2026-09-15`**,
exactly matching 2 of M7's own market predictions' `resolve_by` dates —
confirmed by direct DB read: `market`/`baseline` rows for that same date
now both exist side by side.

Spend: 1 DATA call (the momentum rule's real trailing-return fetch; the
base-rate rule uses its already-frozen constant, no fetch). 0 MODEL.
No commit — no code changed.

## Task M9 — Documentation close-out — **DONE**

`PROGRESS.md`'s "Causal-engine pillar status" section gained a Market
Intelligence subsection: M1-M8 status (all DONE) summarized from this
trace, what's correctly not done (scheduling — human's job; Part C-M's
standing exclusions), the A-M3 contamination wall restated explicitly,
and the standing ≥30-resolved-predictions-per-source success definition
(honestly noted as nowhere near met yet — the ledger holds its first
small cohort, zero resolved).

**Newly authorized this session, done and disclosed rather than silently
decided**: `PROGRESS.md`'s one genuinely stale forward-looking note (the
trading-backtest harness's "only run once credits exist again" caveat)
was updated with a dated addendum confirming that condition is now
satisfied. The historical session-close record of the 5
`test_simulator_e2e.py` failures, from a specific past session's actual
close, was deliberately left untouched — an accurate record of what was
true then, not a standing claim, and rewriting it would misrepresent
history rather than fix a stale note.

Bar: section present, accurate against this trace — **PASS**. Committed.
**Commit**: `1019949`.
**Spend**: 0 (docs only).

## Operational handoff — scheduling (NOT set up by this session; human wires it)

Per the plan's own scope wall (M6/M7: "no auto-scheduling setup — human
wires the schedule"), nothing below has been installed as a real cron
job, launchd plist, or Task Scheduler entry. These are the exact
commands to wire, and the reasoning behind each recommended cadence.

### (a) The resolve script — recommend **daily**

```
0 6 * * * cd /Users/prathamsharma/intent-engine && .venv/bin/python scripts/resolve_market_predictions.py >> logs/resolve_market_predictions_$(date +\%Y-\%m-\%d).log 2>&1
```
(standard crontab syntax; `crontab -e` to install. On macOS a `launchd`
plist with `StartCalendarInterval` at `{Hour: 6, Minute: 0}` works
identically if you prefer that over cron.)

**Why daily, not weekly**: this script is fully unattended-safe —
idempotent by construction (queries only unresolved, due predictions;
a day with nothing due is a real no-op), needs no human input (no
headlines, nothing to draft), and is cheap (≤10 DATA calls per M6's own
budget, typically far fewer since most days resolve 0-2 predictions and
Tiingo/FRED responses are cached). Running it daily keeps each
prediction's `resolved_at` timestamp close to its actual `resolve_by`
date — weekly resolution would let a prediction sit due-but-unresolved
for up to 6 extra days, which is avoidable timing noise in any future
calibration analysis keyed on `resolved_at` (`brier_summary`'s own
`window_days` filter uses exactly that field). 6am is arbitrary but
deliberate: after the prior US trading day's Tiingo data and any
overnight FRED release are reliably available, before market open.

## Session 4 — Cowork standing-cadence checkpoint (2026-07-17)

**Status check, M5-M9 — verified against current `main`, not assumed**: all
five confirmed **DONE** (M5 `45428e0`, M6 `6b7242c`, M7 `01800d7`, M8
`5e0e30b`, M9 `1019949`) — nothing left in the queue to complete. Offline
suite re-run this session: **557 passed, 7 deselected (live), 0 failed** —
green, matches this repo's own prior-session record in
`COWORK-HANDOFF-2026-07-17.md`.

**Daily resolve cadence — first standing run**, `scripts/resolve_market_predictions.py`:
```
Resolved 0 due market/baseline prediction(s) as of 2026-07-17:
  happened:       0
  did_not_happen: 0
  unresolvable:   0
```
Correct no-op — earliest `resolve_by` in the ledger is 2026-08-31 (M7's own
predictions), nothing due yet. 0 DATA calls consumed (no fetch needed when
nothing is due). No code change, no commit.

**Blocker found, not present in prior sessions' record**: `.git/index.lock`,
`.git/HEAD.lock`, `.git/objects/maintenance.lock`, and
`.git/refs/heads/main.lock` are still present in this repo (confirmed via
`ls`), causing `git status`/`git diff` to report false modifications on 5
files (`ROADMAP.md`, `scripts/replay_diagnosis_registry.py`,
`src/intent_engine/core/diagnosis_registry.py`,
`tests/test_diagnosis_registry.py`, `tests/test_pick_next_task.py`) that are
NOT real — verified directly via `git show HEAD:ROADMAP.md` vs the working
tree copy, byte-identical content. Per `COWORK-HANDOFF-2026-07-17.md` §2,
this is the sandbox-mount-can't-unlink-files issue and the fix
(`rm -f .git/*.lock ... && git reset`) must run on the Mac, not from this
session. **No commits were attempted in this repo this session** — the
existing corrupted index makes any `git add`/`git commit` unsafe (real risk
of accidentally staging content from the false diff, the same near-miss the
prior session records twice under §2). Nothing new needed committing this
session anyway (resolve script is a pure no-op read, and the docs work
below was intentionally kept out of git until the lock is cleared).

### (b) The weekly regime report (+ baselines) — recommend **weekly, with one real caveat**

```
0 8 * * 1 cd /Users/prathamsharma/intent-engine && .venv/bin/python scripts/generate_weekly_regime_report.py --entity-id "macro-watch" --headline "<a real, current headline>" --headline "<a second real, current headline>" --output "reports/weekly_regime_report_$(date +\%Y-\%m-\%d).txt" && .venv/bin/python scripts/record_baselines.py --entity-id "macro-watch" >> logs/weekly_regime_$(date +\%Y-\%m-\%d).log 2>&1
```

**Why weekly**: matches the task's own name and the plan's own cadence
intent; also matches `record_baselines.py`'s own purpose (a fresh
baseline cohort recorded alongside each new batch of real market
predictions, sharing a horizon — exactly what this session did manually
after M7).

**The one real caveat, stated plainly rather than glossed over**: the
`--headline` arguments above are placeholders, not something this
command can fill in itself. No news-ingestion vendor is wired into this
phase (out of scope, Part C-M) — this session's own real run used 3
headlines gathered by hand via web search immediately before running the
script. **A literal cron job with static/stale headline text would
silently degrade extraction quality over time** (the same 2 headlines
re-used every week, increasingly disconnected from that week's real
news) — worse than the "correct silence" this system is designed to
produce when evidence is genuinely absent. Recommend one of: (i) keep
this specific step human-triggered weekly (run the command by hand with
fresh headlines, exactly as this session did) until a real
headline-sourcing decision is made and scoped as its own task, or (ii) a
future task designs a real, scoped news-input mechanism before this step
is fully unattended. Not decided here — flagged for your call.

## Session 5 — BA acceleration decisions + implementation (2026-07-18)

Decisions received in writing (user, 2026-07-18), against
`docs/BA_ACCELERATION_PROPOSAL.md`:
1. Daily cadence — **APPROVED as proposed**, implemented this session.
2. Historical backtest track — **HELD** (not approved, not rejected).
   A-M3 NOT amended; zero backtest code written; design doc kept as-is
   for a revisit after first live calibration data (~mid-September).
3. Headline sourcing — **APPROVED** with the proposed 3-feed allowlist,
   implemented this session.
4. Task 3b v2 gate — user runs on the Mac; sandbox attempt recorded in
   overnight_trace.md addendum. Not re-attempted from sandbox.

**Implemented (item 1)**: `core/daily_prediction_policy.py` (pure policy:
allowlist 7 Tiingo + 6 FRED, cap 5/day, 14d floor, buckets {14,30,60,90},
max 2/bucket/day, anti-dup vs unresolved live + within batch, baseline
quota 2/day only when the 60d bucket is used, date-seeded mechanism
rotation + rotating 6th-data-call instrument, $7/mo ESTIMATED spend
ceiling with park-if-exceeded) + `scripts/daily_market_predictions.py`
(thin runner: <=6 DATA + <=2 MODEL calls, numeric-only headlines until
item 3 is wired into it by a future decision, spend log
`data/daily_runner_spend.jsonl`, momentum baseline reuses the snapshot's
SPY series — zero extra DATA calls). 22 offline tests
(`test_daily_prediction_policy.py`, `test_daily_market_predictions_runner.py`).

**Implemented (item 3)**: `core/headline_feed.py` (approved allowlist,
stdlib RSS/Atom parsing, recency <=7d, dedupe keeping digits, top-3 by
deterministic vocab score, provenance rendering, dead-feed degradation,
zero-headline -> numeric-only) + `--headlines-from-feeds` flag on
`scripts/generate_weekly_regime_report.py` (additive; `--headline` path
unchanged; flags mutually exclusive). 9 fixture tests
(`test_headline_feed.py`). Honest allowlist note: Yahoo feed verified
live from the sandbox (application/xml); Reuters/AP URLs unverifiable
from the sandbox (fetch blocked) — kept as approved, protected by the
degradation path; persistent live warnings = human allowlist decision.

**Bars**: full offline suite **588 passed, 0 failed, 7 deselected
(live)** — 557 pre-existing + 31 new, zero regressions. Live first runs
(bar-b-style) happen on the Mac via the cron lines in
`cron_lines_to_install.txt` (human installs; never installed from here).

**Spend**: 0 live model calls, 0 data calls this session (all tests
offline/faked). Sandbox cannot reach the Anthropic API anyway — see
overnight_trace addendum.

**Cron note, stated explicitly**: the weekly cron line deliberately does
NOT include `record_baselines.py` anymore — the daily runner now records
baselines under the approved 2/day cap; keeping the weekly baseline call
would breach that cap on Mondays. Removing it from the recommended line
is cap-compliance, not a change to record_baselines itself (untouched).

## Session 6 — post-review amendments (2026-07-18, user decisions in writing)

1. Task 3b verdict recorded (two consecutive PASSes, bars a+b); **Task 3
   UNPARKED by human review; Task 4 unblocked, pending spec** (details in
   overnight_trace.md addendum; ROADMAP NEEDS-SPEC updated).
2. **Baseline coverage fix (option 1)**: `baseline_quota` now returns the
   daily cap unconditionally — guaranteed 60d baseline accrual every
   trading day; the real <=2/day cap is enforced in the runner against
   the ledger (keyed on resolve_by == as_of+60d, robust under --as-of).
   Honest note: this replaced the 60d-bucket-matching condition I shipped
   earlier the same day, whose stall scenario the user caught in review.
   Option 2 (all-bucket baselines, 3 new frozen base-rate constants)
   recorded as LATER in ROADMAP — deliberately NOT implemented.
3. **FRED '.'-guard amendment** (user-approved deterministic rule, full
   text in macro_data.py docstring): business-daily series drop weekend
   and 1-2-day weekday-holiday '.' placeholders silently (FRED's own
   semantics); >=3 consecutive weekday '.'s, or any '.' in a non-daily
   series (the Oct-2025 shutdown month shape), are GENUINE GAPS —
   excluded, recorded in FredSeries.gaps, warned loudly, and surfaced in
   the rendered report via a "!! DATA GAPS DETECTED" section. None /
   unparseable / empty-after-drops still raise — strictness narrowed to
   FRED's documented semantics, not weakened. One legacy bar updated in
   place as part of the approved change (test_macro_data.py's VIXCLS
   New-Year's-Day fixture: raise -> documented holiday-drop). This
   unbreaks the permanent BAMLH0A0HYM2/CPI/UNRATE weekly failures.

**Bars**: full offline suite **601 passed, 0 failed, 7 deselected** (13
net-new tests incl. 12 gap-rule bars). **Spend**: 0 live calls.

## Overnight loop — Library batch 1 (episodes 1-4) — STAGED AT FOUNDER GATE

Research done for Panic of 1907, Great Depression 1929-33, 1973-74 oil
shock, Volcker disinflation. Output: 3 NEW mechanisms
(debt_deflation_spiral, input_cost_inflation_passthrough,
policy_tightening_demand_collapse) + 3 instance ENRICHMENTS
(credit_contagion x2: Knickerbocker 1907, Caldwell 1930;
supply_shock_propagation: OAPEC 1973). All machine-validated (pydantic
schema, enum subset, id-collision) — one flagged item for founder
distinctness judgment: debt_deflation_spiral's trigger set collides with
leverage_cycle_bust (root cause: no deflation condition in the frozen
enum — recorded on NEEDS-APPROVAL list with
outside_liquidity_backstop_perimeter). Drafts:
docs/library_batch1_draft_entries.json; review sheet:
docs/library_batch1_review_sheet.md. mechanisms.json UNTOUCHED — merge
waits for approval, one data-file commit then. citation_check.sh:
optional only (all 6 URLs verified from sandbox with titles). Spend: 6
fetches, 0 model calls — far under the 40-search/16-call batch ceiling.
Episodes 5-8 NOT started, per instruction.

## Overnight loop — Founder-readable report mockup — STAGED AT FOUNDER GATE

Mockup built 1:1 from the real 2026-07-17 report (no invented numbers;
claim-tracing audit in the design note): docs/report_mockup/
weekly_regime_report_founder_mockup.html + DESIGN_NOTE.md. Format
recommendation: single-file HTML with print-to-PDF (rationale + rejected
alternatives in the note). Honesty markers rendered as features:
UNAVAILABLE badges, "none matched — and that's the finding" card,
always-rendered DATA GAPS section, "0 resolved — no accuracy claimed"
track-record card, per-row provenance. No pipeline wiring — follows
approval. Spend: 0.

## Overnight loop — Marketing workspace (WS4) + cold-outreach package (WS5) — DRAFTS STAGED

WS4: marketing/ stood up per AGENTS.md §3 (no dedicated repo by that doc's
own definition — location decision recorded in its README, movable on
founder preference). Walls declared in README FIRST. Deliverables, all
DRAFT: (a) landing_page_copy.md, (b) sample_structural_analysis_template.md,
(c) weekly_regime_content_formats.md (examples use ONLY the real
2026-07-17 run), (d) publer_pipeline.py — DRY-RUN by design: real mode
double-gated (--real AND founder-created PUBLISHING_ENABLED flag file,
which does not exist) and the real HTTP call deliberately UNWIRED
(NotImplementedError names it a founder-present task). Key read from
.env at runtime only in real mode, never printed/copied — dry-run never
touches it. 5 wall tests (test_publer_pipeline_walls.py). Every claim in
every draft carries an inline trace to a gate-passed capability or
ledgered fact; the only performance statement anywhere is the explicit
no-accuracy-claim disclaimer.

WS5: marketing/outreach/ — 3 message variants (DM, email, one follow-up
max), offer one-pager, append-only tracking-ledger schema mirroring
prediction_ledger's latest-row-per-id convention, with the
job-application dry-run/real wall stated as invariant #2 (no "sent" row
without prior approval row + non-null approved_by). NOTHING sent,
scheduled, or published. Spend WS4+WS5: 0 live calls, 0 fetches.

## Overnight loop 2 (2026-07-19/20) — morning decisions recorded

Received and recorded VERBATIM state: decisions 2 (library batch 1
APPROVED AS-IS, enum candidates DEFERRED until after batch 3) and 3
(report mockup APPROVED, wire renderer) are fully specified — EXECUTED
below. Decisions 1 (T005 live-bar result), 4 (marketing drafts), the
approval half of 5, and the cron-confirmation half of 6 arrived with
UNFILLED template brackets ("[PASTE RESULT...]", "[APPROVED AS-IS /
...]", "[YES/NO...]") — per park-don't-improvise these are NOT assumed:
T005 closeout PARKED (disk check corroborates: no t005-live entity-memory
rows, no new logs — the runs appear not to have happened yet); marketing/
outreach drafts remain DRAFT-pending-approval; cron confirmation goes
back on the morning list. Decision 5's placeholder VALUES ([X days]=3
business days, [segment]=early-stage B2B founders) and decision 6's
four ambiguity-recommendation acceptances were affirmatively stated and
ARE acted on.

## Overnight loop 2 — batch-1 merge EXECUTED + a protocol violation, owned

Merge done per decision 2: 3 new mechanisms + 3 enrichments ->
mechanisms.json now 20 entries; bar (e) PASS (both extraction prompts
sha256-identical before/after; simulator 2067d21a..., regime_report
fb19551507...). **Violation, recorded honestly**: the merge commit
(af0dc9d) landed while the suite showed 3 failures — my commit chain
gated on the wrong pipeline exit status. All 3 failures were legitimate
consequences of the approved merge, fixed FORWARD (no history rewrite):
(1) exact-ID-set test updated 17->20 (same precedent as its own M3
update); (2) batch-1 citation strings reformatted URL-first to conform
to the EXISTING strict test convention — bar kept strict, data conformed;
(3) the unused-condition no-catch-all test rewritten to assert its intent
directly (batch 1 consumed the last unused condition; matching
inflation_rising is now correct declared behavior). Suite after fixes:
**617 passed, 0 failed** (exit code checked this time). Enum candidates
remain DEFERRED per decision; enum and prompts untouched.

## Overnight loop 2 — Report renderer wired + FIRST real founder report (decisions 3, WS3)

scripts/render_founder_report.py: deterministic .txt->HTML transform in
the approved mockup style; parse-park (RAISES on unrecognized shape, never
guesses); track-record card is DATA-DRIVEN (0-resolved card only while
calibration says "no resolutions yet", else renders ledger counts
verbatim); assert_language_walls on the final artifact. 10 bars
(test_render_founder_report.py) incl. golden-file from the REAL 2026-07-17
report + a no-invented-numbers test (every HTML P-value must exist in the
source). Wired additively into generate_weekly_regime_report.py via
--founder-html (requires --output; old paths untouched).

FIRST real founder report generated (WS3 demo asset, production data
only): reports/weekly_regime_report_2026-07-17.founder.html — 3
UNAVAILABLE badges, none-matched card, no-gaps line, 0-resolved
no-accuracy card, P-values {0.58,0.65,0.72} identical to source.
Saved alongside the raw .txt. Suite 627 passed. Spend: 0 live calls.

## Overnight loop 2 — Library batch 2 (episodes 5-8) — STAGED AT FOUNDER GATE

Episodes: 1987 Black Monday, Japan bubble ~1990, Asia 1997, LTCM 1998.
Output: 2 NEW mechanisms (mechanical_feedback_liquidation [1987] --
FLAGGED trigger-set collision with margin_collateral_spiral, same class
founder accepted in batch 1; crowded_trade_deleveraging [LTCM] -- clean
distinct set) + 2 ENRICHMENTS (reflexive_bubble: Japan 1990;
credit_contagion: Asia 1997 regional contagion) + 1 PARKED mechanism
(currency_peg_break_contagion -- Asia's true mechanism needs a peg
condition the frozen enum lacks; recorded as NEEDS-APPROVAL candidate #3,
mechanism parked, enum NOT widened, exactly as instructed). All
machine-validated (schema/enum/id/dedup). Two citations
PENDING-MAC-VERIFICATION (LTCM Fed speech returned empty from sandbox;
Japan IMF PDF returned 200 application/pdf but oversized) -- routed to
citation_check.sh per amendment 2; these two require a real 200 before
merge. mechanisms.json UNTOUCHED; NO data-file commit. Batch 3 NOT
started. Drafts: docs/library_batch2_draft_entries.json; review sheet:
docs/library_batch2_review_sheet.md. Spend: 7 fetches, 0 model calls.

## Overnight loop 2 — AP feed decision-prep (WS5 item 5)

AP Business (apnews.com/hub/business?output=rss) is BLOCKED by the
web-fetch tool (HTTP 403 cowork_web_fetch_url_blocked), same class as
Reuters -- not dead, but unusable from the sandbox and NOT routed around
(standing web-content rule). Net: 2 of 3 approved feeds (Reuters, AP) are
unusable; only Yahoo verified-working. Degradation path keeps it safe but
thin. Verified replacement candidates: NPR Business
(feeds.npr.org/1006/rss.xml -- clean text/xml, parser+scorer confirmed on
real fetched items; RECOMMENDED), MarketWatch MarketPulse (Dow Jones
public feed, application/xml 200, markets-focused, couldn't render items
in sandbox -- needs founder eyeball), CNBC (empty body -- skip).
Secondary finding surfaced, NOT acted on: REGIME_VOCAB misses
IPO/merger/singular-"stock" headlines -- flagged as optional tuning task,
vocab untouched (shared tested surface). NO allowlist change made.
Decision-prep: docs/AP_FEED_DECISION_PREP.md. Spend: 4 fetches.

## Overnight loop 2 — Outreach finalization (WS6 item 6)

Send-ready variants produced with founder-affirmed placeholder values
(3 business days, early-stage B2B founders); per-recipient fields stay
unresolved until real-research approval time. Per-message approval
checklist template (message + recipient + claim-trace audit + one-follow-
up gate). ledger.jsonl initialized EMPTY. Same dry-run/real wall: no
status="sent" row without a prior approved row + non-null approved_by.
NOTHING SENDS. Note: decision 4 (marketing drafts) and the approval-half
of decision 5 arrived as unfilled brackets, so those drafts remain
DRAFT-pending-approval -- no revisions applied (none were specified);
only the affirmatively-given placeholder VALUES were applied. Spend: 0.

## Overnight loop 3 (2026-07-20/21) — bracket fields unfilled AGAIN; gated items parked

The four fields (A T005 result, B marketing drafts, C outreach, D
citation_check) and ALL standing decisions (batch-2 verdict, Task 5,
AP feed, vocab) arrived as unfilled option-menus ("[opt1 / opt2 / opt3]"),
no selection marked. Per the founder's OWN stated rule ("empty brackets =
parked again") and the park-don't-improvise wall, all of item 1 is PARKED,
not guessed:
- A unfilled -> T005 stays LIVE-BARS-PENDING-HUMAN (disk still shows no
  t005-live rows / no new run logs; consistent).
- Batch-2 verdict + D unfilled -> NO batch-2 merge (a real data-file
  commit gated on an actual approval + verified citations; neither
  present).
- B/C unfilled -> marketing/outreach stay DRAFT-pending-approval.
- AP-feed + vocab unfilled -> allowlist and REGIME_VOCAB untouched.
- Task 5 verdict unfilled -> T006 not implemented, stays a proposal.
Item 2 (batch 3) is explicitly gated on batch-2 feedback being filled ->
NOT filled -> batch 3 NOT started; the 12-episode curriculum stops at 8
studied (batch 1 merged, batch 2 drafted-pending).
Ungated work executed instead: item 3 (library inventory, honest
current-state, pre-batch-3) and item 4 (capability-boundaries memo) --
both analysis-only, no gated actions, no accuracy claims. Item 5 (Task 5
impl) skipped -- not approved. Guessing "approve" on any of the above
would cross a real wall (data-file merge / allowlist change / code into
queue) -- declined by design.

## Overnight loop 3 — items 3 & 4 (ungated analysis docs) DELIVERED

Item 3: docs/MECHANISM_LIBRARY_STATE.md -- INTERIM inventory (labeled
8/12 episodes, since batch 3 is gated-not-started). Current live library
20 entries (3 multi-instance, 17 single, 0 speculative), batch-2 drafts
pending, 1 park recorded (currency-peg), 4 deferred enum candidates mapped
with what each unlocks. Zero accuracy claims. Item 4:
docs/CAPABILITY_BOUNDARIES.md -- plain statement of the 4-item DO surface
+ the 4 absent capabilities (strategy backtest HELD/A-M3; technical
analysis absent+contested; company/fundamental absent+new-data; TimesFM/
Kronos LATER-gated), each with what-it-would-take / gate-hit / and the
explicit "does it move accuracy before calibration? No" with the single
shared reason (0 resolved predictions). Both docs analysis-only, no code,
no gated actions. Item 5 (Task 5 impl) skipped -- unapproved. Suite 627
green (explicit exit-code check before each commit, per the process
guard). Spend loop 3: 0 fetches, 0 model calls.

## Overnight loop 4 (2026-07-21/22) — fields unfilled a 4th time; per-field status

A/B/C/D and all standing picks arrived as menus again ("opt / opt /
feedback"), no selection. Per the founder's explicit rule ("a selection,
not a menu ... menu-style = parked a fourth time, nothing below item 4
runs") and park-don't-improvise:
- A (T005 result): PARKED -> T005 stays LIVE-BARS-PENDING-HUMAN.
- B (marketing drafts): PARKED -> DRAFT-pending-approval.
- C (outreach package): PARKED -> DRAFT-pending-approval.
- D (citation_check): PARKED -> batch-2 citations unverified.
- Batch-2 verdict / Task 5 / AP feed / vocab: PARKED (unfilled menus).
Item 1 (execute filled fields): nothing filled -> PARKED, no commits.
Item 2 (batch 3): gated on batch-2 verdict filled -> NOT filled -> NOT
started; curriculum stays 8/12. Item 5 (Task 5 impl): unapproved -> skip.
Ungated work executed: item 3 (mechanism-explanation-depth SPEC -- design
only, my-approval-before-build) and item 4 (docs/POSITIONING.md -- analysis
only). No enum/prompt/allowlist touched; mechanisms.json still 20. Spend:
0 fetches, 0 live model calls.

## Overnight loop 4 — items 3 & 4 (ungated) DELIVERED

Item 3: docs/MECHANISM_EXPLANATION_DEPTH_SPEC.md (T007) -- SPEC ONLY.
Key design finding: causal_chain + cited instances already exist per
mechanism, so explanation depth is DETERMINISTIC RENDERING (0 live calls,
fully offline-testable), not a new model call. 6 bars: condition
traceability, cited-instance presence, causal-chain verbatim fidelity,
no-prediction grep walls, correct silence, additive/no-regression. Build
gated on approval. Item 4: docs/POSITIONING.md -- analysis-only thesis
(moat = verified code-graded forward calibration + transparent method,
NOT an accuracy number; incumbents measure plan-vs-actuals or backtested
hit-rates, neither = verified forward calibration; faking a number before
Sep destroys the trust that IS the product; what's sellable now =
transparent structural analysis + explanation depth). Zero accuracy
claims in either doc. Suite 627 green (explicit exit-code check before
each commit). Spend: 0.

## Overnight loop 5 (2026-07-22) — T007 build: PARKED at build time (honest bar conflict)

Received context (not acted on this loop, per T007-only scope): A =
BOTH T005 live bars PASS (supplier decision renders 4 mechanisms incl.
concentrated_supplier_base; neutral decision renders no section) -- T005
DONE-flip deferred to next message. D = citation_check 9/10 200; the LTCM
Treasury PWG PDF (home.treasury.gov/.../hedgefund.pdf) 404 -> that batch-2
citation needs a swap before merge; Japan IMF PDF cleared 200. Neither
acted on this loop.

T007 (APPROVED as specced) build BEGUN; a bar-(d) pre-check against real
data (before any committed code) found bars (c) and (d) MUTUALLY
UNSATISFIABLE on the real library: bar (c) requires verbatim causal_chain
steps; bar (d) forbids buy/sell/forecast across the whole block; 6
mechanisms (margin_collateral_spiral, carry_trade_unwind,
money_market_contagion, winners_curse_acquisition, debt_fueled_capacity_race)
use those words in verbatim third-person historical descriptions.
PARKED rather than unilaterally narrow bar (d) to ship my own approved
feature (park-don't-improvise; Honest Park > crossed wall). Full finding +
3 resolution options + recommendation: docs/T007_PARK_FINDING.md. No code
committed; suite green 627 (explicit exit-code check). Spend: 0.

Real --explain block the feature produces (deterministic, from the CLEAN
supply_shock_propagation entry -- the founder asked to see real output):

    Why this may be in play — Supply-shock propagation (well_documented)
      Conditions present in your situation:
        - concentrated_supplier_base
        - few_dominant_competitors
      How it unfolds (documented pattern):
        1. A small number of suppliers account for most of an industry's critical input
        2. An external shock removes capacity from that supplier base
        3. Buyers relying on just-in-time inventory have no slack to absorb the gap
        4. Production halts cascade downstream faster than new supply can be qualified
        5. Recovery lags the shock by quarters to years
      Historical precedent: 2020-2023 global semiconductor chip shortage (2021)
      Source: <cited URLs>

(margin_collateral_spiral's block would be identical in shape but trips
bar (d) on the verbatim step "...is forced to sell the underlying asset...".)

## Overnight loop 6 (2026-07-22) — T007 BUILT TO GREEN (option 1, founder-ratified)

The (c)/(d) conflict from loop 5 resolved by OPTION 1 (ratified): language
wall scoped to SYSTEM-AUTHORED framing lines; verbatim causal_chain steps +
cited source EXEMPT (bar (c) guarantees they're unedited historical
quotes, not the system's voice -- which is what "no predictions in the
system's voice" protects). render_mechanism_explanation +
assert_explanation_system_walls added to simulator/mechanism_section.py
(0 model calls -- a model call here is a park condition); --explain CLI
flag (off by default, additive, one-liner path byte-identical per bar f).
8 bar tests (tests/test_mechanism_explanation.py), all against the REAL
20-mechanism library. All six bars pass:
(a) condition-traceability, (b) cited-instance presence, (c) verbatim
causal-chain fidelity, (d) system-line wall, (e) correct silence,
(f) additive/no-regression. Suite 635 passed (627+8), explicit exit-code
check (EXIT=0) before commit. Spend: 0.

THE PROOF (real --explain block, wall-tripping mechanism carry_trade_unwind
-- verbatim history contains 'sell'/'buy', system framing stays clean):

    Why this may be in play — Carry-trade unwind (well_documented)
      Conditions present in your situation:
        - interconnected_counterparty_exposure
      How it unfolds (documented pattern):
        1. Investors borrow in a low-interest-rate funding currency and invest
           the proceeds in higher-yielding assets ...
        3. ... prompting leveraged holders to unwind (sell the target-currency
           asset, buy back the funding currency to repay the loan)
        4. The unwinding itself pushes the funding currency higher ...
      Historical precedent: August 2024 global market selloff following the Bank
        of Japan's rate hike ... (Nikkei -12.4% in a single day) (2024)
      Source: https://www.bis.org/publ/bisbull90.pdf (BIS, 'The market turbulence
        and carry trade unwind of August 2024')

The verbatim "unwind (sell ... buy back ...)" renders (bar c) while the
system-authored header/labels carry zero forbidden terms (bar d, option 1).
ROADMAP T007 -> DONE.

## Overnight loop 7 (2026-07-22) — backlog clearance: T005 DONE + batch-2 MERGED

BATCH-2 MERGE (founder verdict: APPROVE AS-IS, incl. the flagged
mechanical_feedback_liquidation dual-match collision -- same class accepted
in batch 1): 2 new mechanisms (mechanical_feedback_liquidation [1987],
crowded_trade_deleveraging [LTCM 1998]) + 2 enrichments (reflexive_bubble
+Japan 1990; credit_contagion +Asia 1997) merged -> mechanisms.json now
**22 entries**. currency_peg_break_contagion stays PARKED (enum-frozen).
LTCM citation swapped per founder: 404'd Treasury /276/hedgefund.pdf ->
/236/hedgfund.pdf (sandbox web_fetch confirmed ~140KB real Treasury PDF =
reachable; citation_check.sh updated for the authoritative Mac run;
sechistorical.org mirror added). bar (e): extraction prompts sha256-
identical before/after merge -- PASS. ID-set test updated 20->22. Suite
635 passed, EXIT=0 (explicit check before commit). Enum candidates (now 4)
remain DEFERRED until after batch 3. Batch 3 now unblocked by this merge.

## Overnight loop 7 — remaining clearance + Phase 1 cadence-v2 proposal

Task 5 (T006) -> runnable queue (spec approved). AP feed: Reuters+AP
dropped (web-fetch-blocked), NPR Business added (verified) -- allowlist +
test updated, suite green. REGIME_VOCAB widening: SPEC ONLY
(docs/REGIME_VOCAB_WIDENING_SPEC.md, T008) -- add ipo/merger/acquisition/
stock/buyback/guidance, bars written, awaiting approval before merge.
Marketing + outreach drafts: recorded APPROVED-AS-DRAFTS in marketing/
README (PUBLISHING_ENABLED uncreated, per-message send wall stands --
approval does not move anything past dry-run).

PHASE 1 (densification): docs/CADENCE_V2_PROPOSAL.md -- widened FORWARD
surface for MY approval, NOT implemented. Proposes instrument allowlist
13 -> ~30 (9 more sector ETFs + broad/intl/credit ETFs + 7 more FRED
macro series, all deterministic + pydantic-validated), daily cap 5 -> 8
(fills 4 horizon buckets at 2 each), ceiling stays $7 (breadth adds $0
data calls, not model calls; model-call estimate ~$1.68/mo). All quality
guards (rotation, horizon staggering, anti-dup, baselines, correct
silence, A-M5 wall) unchanged. Three explicit approvals requested:
allowlist, cap, ceiling. Code staged, not built.

LEDGER GROWTH SNAPSHOT (2026-07-22): 9 total predictions (7 market, 2
baseline), 0 resolved; instruments SPY x6 + 3 macro; resolve_by window
2026-08-31 .. 2026-10-16; FIRST resolution 2026-08-31. Toward the
>=30-resolved-per-source gate: densification (cadence-v2) is what closes
that gap; daily generation runs on the Mac (no sandbox Anthropic egress).
Spend loop 7: 0 live calls; 1 web_fetch (LTCM citation verify).

## Overnight loop 7 — Library batch 3 (episodes 9-12, FINAL) — STAGED AT FOUNDER GATE

Unblocked by the batch-2 merge this loop. Honest finding: episodes 9-12
are mostly ALREADY COVERED -- dot-com (reflexive_bubble/winners_curse/
capex_overbuild) and GFC (credit_contagion/leverage_cycle_bust/
money_market_contagion/bank_run) are already in the library. Batch 3 =
1 NEW mechanism (exogenous_activity_halt [COVID 2020, NBER-cited] --
FLAGGED trigger-set collision with mechanical_feedback_liquidation +
margin_collateral_spiral, same dual-match class accepted in batches 1-2)
+ 2 ENRICHMENTS (input_cost_inflation_passthrough +2021-22 CPI 9.1%;
policy_tightening_demand_collapse +2022-23 hiking ~525bp -- both citations
PENDING-MAC) + 1 PARKED (securitized_credit_opacity -- GFC opacity needs a
condition the enum lacks; its expressible set collides with
money_market_contagion -> enum candidate #5). mechanisms.json UNTOUCHED;
NO data-file commit. Review sheet: docs/library_batch3_review_sheet.md;
drafts: docs/library_batch3_draft_entries.json. Completes the 12-episode
curriculum. Enum-candidate list now COMPLETE at 5 -- ready for the batched
enum decision. Spend: 3 fetches, 0 model calls.

## Overnight loop 8 (2026-07-19) — batch-3 MERGED: curriculum COMPLETE at 12/12

BATCH-3 MERGE (founder verdict: APPROVE AS-IS, incl. the flagged
exogenous_activity_halt dual-match collision -- third ratified member of
the drawdown_gt_20pct class after 1987/2021): 1 new mechanism
(exogenous_activity_halt [COVID 2020, NBER-dated]) + 2 enrichments
(input_cost_inflation_passthrough +2021-22 CPI ~9.1%;
policy_tightening_demand_collapse +2022-23 ~525bp hiking cycle) merged ->
mechanisms.json now **23 entries**. Both PENDING-MAC citations cleared
BEFORE merge: bls.gov/cpi and federalreserve.gov/monetarypolicy/
openmarket.htm each returned HTTP 200 with full real page content via
web_fetch 2026-07-19 (the Fed page even renders the 2022-23 rate-action
tables the citation cites). securitized_credit_opacity stays PARKED.
bar (e): extraction prompts sha256-identical before/after merge
(regime_report fb19551507..., simulator 2067d21a...) -- PASS. ID-set test
updated 22->23. MECHANISM_LIBRARY_STATE.md rewritten to the final 12/12
map. ENUM DECISION (founder, post-batch-3, against the complete 5-candidate
list): **KEEP FROZEN -- all 5 DEFERRED**, recorded in the state doc.
Suite 635 passed, 0 failed, 9 deselected (live/networked), EXIT=0
(explicit check before commit). Note: this session runs in a fresh
sandbox; a stale .git/index.lock from an interrupted prior git op was
found (worktree verified byte-identical to HEAD 0ec7503 before any work);
commits use a separate GIT_INDEX_FILE -- founder can rm the lock file.

## Loop 8 — T008 MERGED: REGIME_VOCAB widened +6 (founder approved)

Added ipo, merger, acquisition, stock, buyback, guidance to
core/headline_feed.REGIME_VOCAB (36 -> 42 terms; additive only, scoring
logic untouched). All spec bars asserted as tests: (a) additive-by-
exactly-6 with every pre-existing term still present, (b) the three real
NPR miss titles now score >=1, (c) 4 non-markets control titles still
score 0 (no term dropped -- park condition not triggered), (d) scoring
deterministic/unchanged. Suite 639 passed, 0 failed, EXIT=0 (explicit
check before commit). This is the headline vocab surface -- NOT the
frozen TriggerCondition enum, which stays frozen per the loop-8 decision.

## Loop 8 — CADENCE V2 IMPLEMENTED (founder approved all three numbers)

Founder approvals recorded: allowlist as proposed (22 Tiingo incl. all 11
GICS sector SPDRs + DIA/MDY/EFA/EEM/HYG/LQD; 12 FRED incl. DGS2/DGS30/
T10YIE/DTWEXBGS/DCOILWTICO/DEXUSEU -- 13 -> 34 instruments), DAILY_CAP
5 -> 8 (max-per-bucket stays 2; 8/day = 4 buckets x 2 by construction),
ceiling $7 UNCHANGED. Implementation: rotating extra generalized to a
deterministic 5-instrument daily window over the 29-entry non-core pool
(start steps by window size; gcd(5,29)=1 so all 29 visited in 29 days,
asserted as a test); run budget <=10 data + <=4 model calls;
allowed_instruments_today = 4 core + SPY + today's 5 extras (grounding
discipline intact); drafting schema maxItems tracks DAILY_CAP
automatically. Tests: v2 allowlist exact-set, cap/ceiling numbers,
window determinism/size/no-dupes/full-coverage, allowed-today shape,
cap-enforced-at-8 with 9-candidate spread, budget shrink at cap-1.
Suite 644 passed, 0 failed, EXIT=0 (explicit check before commit).
NOT changed: grading, claims, baseline pairing, anti-dup, 14d floor,
park-if-exceeded, append-only ledger, >=30-resolved Alpaca wall.
The widened cadence only goes LIVE when the daily job runs on the Mac
(sandbox has no Anthropic egress) -- that remains the founder's single
biggest lever on calibration timing.

## Loop 8 (cont.) — T009 BUILT: synthetic-world reasoning eval (founder approved + raised to HIGH priority)

Founder decisions mid-loop: (1) Phase 3 = the EVALUATION variant (fictional
companies/industries/events with constructed outcomes; explicitly NOT model
training); (2) priority raised from low to HIGH; (3) "make the synthetic
examples as close to the real world as possible; work the base well" —
implemented as analyst-brief realism (seeded magnitudes in realistic
ranges, fictional rivals/lenders/regulators, healthy-metrics control
worlds that bait topical hallucination).

Built: core/synthetic_worlds.py (deterministic generator, 89 worlds =
23x3 single + 12 mixed + 8 control; 6-part leakage wall: no enum token,
no enum phrase, no mechanism id/name, no real-world anchor incl. banned
years, no 8-word library shingle, enum-valid plants; fictional-entity
disjointness wall) + scripts/run_synthetic_world_eval.py (offline leg run
THIS loop; live leg STAGED for Mac: frozen extraction prompt used
READ-ONLY with sha256 2067d21a... asserted before any call, <=100-call
cap, ~$1.78 estimate, park semantics, no ledger writes) + 16 bar tests.

OFFLINE RESULTS (reports/synthetic_worlds_eval.md/.json): constructed
truth recovered 89/89 by construction; the extracted learning is the
ENUM EXPRESSIVENESS MAP — only 11/23 mechanisms uniquely identifiable on
their own best evidence; 6 tied classes derived incl. the 6-member
credit-side class and the 5-member drawdown class; cross-checked
33 = 3x11 unique-top singles. Recorded as EVIDENCE for the deferred enum
decision, no recommendation. Report carries the scope disclaimer +
language walls (no accuracy-claim phrasing; tested).

The reasoning test proper is the LIVE leg (narrative -> frozen extraction
prompt -> matcher): one Mac command. Honest caveat recorded in the
script: the frozen prompt says "business decision's description"; briefs
are close but not identical — poor extraction on briefs would be a
FINDING, never a prompt patch (edit re-opens the Task 3 gate).

Suite 660 passed (644 + 16), 0 failed, EXIT=0 explicit check. Walls: 0
model calls; prompts/enum/library untouched; nothing published; training
use of the generator would be a separate founder-gated capability.

## Loop 8 (cont.) — T006 WIRED (founder green-light via morning-list continuation)

Built to the approved spec (docs/TASK5_WIRING_SPEC_PROPOSAL.md), T005's
shape mirrored exactly: run_premortem gains bridge_client /
bridge_entity_id / bridge_ledger_path kwargs (explicit ValueError if
client without entity id); additive PremortemResult.ledgered_predictions
(default None -- every existing caller unaffected, constructor-compat
tested); CLI --record-predictions flag (off by default, zero extra calls
otherwise) + plain stderr confirmation via _record_confirmation() with a
word-boundary language bar (no will/forecast/accurate/P=). Combined
analyzer prompt UNTOUCHED (A3); bridge drafting prompt untouched (frozen
substrate); no auto-resolution/scoring/backfill (scope wall stands).
Bars (b)(c)(d)(e) asserted offline (7 tests incl. append-only proof
against a pre-existing ledger row + exactly-one-drafting-call): bar (a),
the real live run recording 1-3 rows, is MAC-PARKED within the spec's
<=6-call budget -- command:
  .venv/bin/python -m intent_engine.simulator.cli --entity-id <id> \
    --decision "..." --record-predictions
Suite 667 passed (660 + 7), 0 failed, EXIT=0 explicit check. 0 sandbox
model calls.

## Loop 9 (2026-07-20) — T006 bar (a) PASS (founder-run) -> T006 DONE

Founder ran the live fixture (4-person outbound sales hire pre-PMF,
entity t006-live): 20.4s, one drafting call + one transient-length retry
(claim 328 chars vs 300 cap -> auto-retry PASS; within the <=6-call
budget; recurrence worth watching, noted). 3 predictions recorded.
DIRECT DB VERIFICATION (sandbox, this loop): 3 rows source="premortem",
entity t006-live, p in {0.72, 0.65, 0.58} (all 0<p<1), resolve_by
{2026-11-20, 2027-01-20, 2027-01-20} (all strictly future), claims
resolvable (pipeline count, runway months, roadmap-iteration presence).
Pre-existing 9 market/baseline rows untouched -- append-only held.
All six bars now PASS -> ROADMAP T006 flipped DONE.

## Loop 9 — T009 LIVE RUN HARVESTED (founder-run) + generator v1.1

Founder ran the live leg (89 calls, ~$1.78, frozen-prompt hash verified).
Headline: recall 1.00 (no planted causal symptom ever missed on fully
fictional inputs), 68/69 singles + 12/12 mixed recovered. Key negative
finding: precision 0.68 from ONE systematic artifact -- the v1.0 opener
named a "principal competitor" in every world and the extractor read it
as few_dominant_competitors 67 times (also costing 5/8 control silences
and the single miss, winners_curse_acquisition 2/3). Honest attribution:
generator artifact first, model over-trigger second. FIX (base v1.1, per
the founder's "work the base well" directive): conditional opener --
concentrated phrasing only where the condition is planted, broad-field
counter-evidence phrasing everywhere else; +1 test (17 total), walls
unchanged, offline report regenerated, v1.0 live record preserved in
reports/synthetic_worlds_eval_live.md with the analysis appended. v1.1
live numbers need one fresh Mac run (same command). NO prompt/enum/
library change; training use still gated.

## Loop 9 (cont.) — T009 run 2 (v1.1, founder-run) harvested + harness made append-only

RUN 2 RESULTS (89 calls, same seed): singles 68/69 (same lone miss --
winners_curse world 2, where a hallucinated capacity_investment condition
combined with the planted valuation condition to rank capex_overbuild
first), mixed 12/12, **controls 8/8 clean** (from 3/8), condition recall
1.000 (again: zero planted symptoms missed across both runs), precision
0.677 -> **0.907**; few_dominant_competitors hallucinations 67 -> 9.
Reading: the v1.1 opener fix removed the dominant artifact; the residual
~9% imprecision (mostly few_dominant_competitors x9 + adjacent credit-
family conditions) is now plausibly model over-trigger, but ONE clean
control run does not establish stability -- the live leg is
non-deterministic on fixed worlds, and 3/8 -> 8/8 across two runs is
itself the variance measurement (founder's point, adopted).

TWO FOUNDER-FLAGGED HARNESS DEFECTS FIXED:
(1) stale template line ("hallucinated conditions on the rest") rendered
even in the all-clean case -> control line is now conditional (tested);
(2) worse, run 2 OVERWROTE run 1's report/JSON (run 1 recovered from git
26c575d) -> record_live_run() now archives every run to
reports/synthetic_worlds_runs/<run_id>.json, appends a summary row to
reports/synthetic_worlds_run_history.jsonl (append-only), and regenerates
the latest report WITH the cross-run history table. Both founder runs
backfilled into the history (v1.0: 3/8 clean, prec 0.677; v1.1: 8/8,
prec 0.907). e2e test extended to cover archiving + history + conditional
wording. Suite 668 passed, EXIT=0. Stability question stays OPEN: 2-3
more v1.1 runs (~$1.78 each) would bound the control-hallucination rate.
