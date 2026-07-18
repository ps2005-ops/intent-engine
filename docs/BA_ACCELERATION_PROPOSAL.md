# Business-analyst agent — training-loop acceleration proposal (2026-07-18)

*Proposal only. Nothing below is implemented. Items 1 and 2 require your
explicit approval before any code is written; item 2 additionally requires a
written amendment to the A-M3 wall (see the conflict section — this is the
single most important thing in this document). Hard constraints restated and
honored throughout: no early resolution of live predictions except by their
own rules; Alpaca gated behind ≥30 LIVE resolved + human calibration review;
park-don't-improvise; spend tracked per task.*

---

## 1. Daily prediction cadence + budget (proposal)

**Current state**: 7 ledgered predictions (5 market, 2 baseline), zero
resolved, generation is weekly-at-best and human-triggered with hand-fed
headlines. First resolutions land 2026-08-31.

**Proposed cadence — "daily dense, capped":**

- **Generation**: every trading day (Mon–Fri), one run of the existing
  M7 pipeline (regime snapshot → extraction → drafting), targeting
  **3–5 machine-resolvable predictions/day, hard cap 5** (enforced in
  code, not prompt). Days with genuinely no signal produce fewer or zero
  — correct-silence discipline unchanged.
- **Instrument menu (deterministic, not model-chosen)**: expand from
  {SPY, T10Y2Y, UNRATE} to a fixed allowlist already compatible with the
  two existing resolution sources (no new source types, no schema
  change): Tiingo — SPY, QQQ, IWM, TLT, GLD, XLE, XLF; FRED — T10Y2Y,
  UNRATE, CPIAUCSL, BAMLH0A0HYM2, DGS10, VIXCLS. The drafting call may
  only emit rules against the allowlist; anything else is rejected at
  record time (same pydantic-validation pattern as M5).
- **Mechanism rotation**: deterministic date-seeded rotation across the
  mechanism families (curve, credit, inflation, labor, drawdown,
  momentum) so density doesn't collapse into "five SPY drawdown bets a
  day." Rotation is code, not model choice.
- **Staggered horizons**: each day's batch must spread across horizon
  buckets {14d, 30d, 60d, 90d} — enforced by a pre-insert check.
  Minimum horizon floor 14d (shorter is noise). Result: resolutions
  arrive continuously from ~2 weeks after start instead of clumping.
- **Anti-duplication guard**: reject a new prediction whose
  (instrument, rule type, direction, horizon bucket) duplicates an
  unresolved live prediction — deterministic pre-insert check. Density
  without redundancy.
- **Baselines**: per day, record matching baselines only for horizon
  buckets that received a market prediction that day (max 2/day) —
  keeps market-vs-baseline comparable at every horizon without letting
  baselines outnumber the engine.

**Budget (per day / per month):**

| Item | Per run | Monthly (~21 trading days) |
|---|---|---|
| MODEL calls | ≤4 (1 extraction + 1 drafting + ≤2 retry) | ≤84 |
| DATA calls | ≤6 (snapshot cached per day) | ≤126 |
| Est. dollar cost | ~$0.10–0.30 | **≤$7/mo ceiling** (park if exceeded) |

Tiingo/FRED free tiers comfortably cover ≤6 data calls/day. Ledger
accrual: ~60–100 predictions/mo; **the ≥30-resolved-per-source Alpaca
precondition is realistically reached mid-to-late September** (14d/30d
buckets resolving from late August) instead of some time in Q4.

**Unchanged gates**: daily resolve stays rule-driven only; no
calibration feedback into generation until ≥30 live resolved per source
AND your review; append-only ledger; scheduling wired by you, not the
agent.

**Open for your decision**: (a) approve instrument allowlist, (b)
approve the $7/mo ceiling, (c) daily runs need headlines or run
numeric-only until item 3 lands — recommend numeric-only start
(honest input, zero fabrication risk) with headline enrichment once
item 3 is approved.

---

## 2. Historical backtesting protocol ("backcast track") — DESIGN ONLY

### ⚠️ Direct conflict with the A-M3 wall — decision required first

A-M3 as written (PROGRESS.md ~L2979): *"the LLM is never evaluated by
'paper trading in the past'… Evaluation is FORWARD… This wall does not
expire and does not get relaxed by a future session finding it
inconvenient."* A historical backtest is exactly what this bans, and you
asked for acceleration "without weakening any gate." I am not designing
around this silently: **the protocol below is contingent on you
explicitly amending A-M3 in PROGRESS.md**. Proposed amended wording:

> Live evaluation is FORWARD only. A separate, quarantined BACKTEST
> track may measure the pipeline against pre-registered historical
> episodes under the protocol in docs/BA_ACCELERATION_PROPOSAL.md §2,
> provided: its results never modify any rule, threshold, prompt, or
> mechanism entry; never count toward any live gate (including Alpaca's
> ≥30-resolved); and are never cited as evidence of live engine skill.
> Tuning against historical outcomes remains permanently banned.

If you don't sign that amendment (a dated line in PROGRESS.md is
enough), item 2 stays parked and nothing is built.

### Protocol design

**Separate ledger, structurally unmixable**: `data/backtest_ledger.db`,
identical schema; sources `backtest_market`/`backtest_baseline`
(additive Literal extension). Live calibration functions take an
explicit source whitelist and **refuse** backtest sources (unit-tested),
and vice versa. No query in the live path ever opens the backtest DB.

**Pre-registered episodes**: a fixed episode list (proposed: 12 —
4 stress, 4 recovery, 4 quiet regimes; exact dates enumerated in the
spec at approval time) chosen and committed BEFORE the first model
call. Adding/removing episodes after first run requires new written
sign-off — prevents cherry-picking by construction.

**Information hiding (no lookahead), deterministic**:
- Snapshot for as-of date T contains only observations whose
  *publication* date ≤ T: prices = Tiingo EOD ≤ T; FRED series lagged by
  their real publication delay (per-series lag constants; e.g. UNRATE
  for month M publishes ~first Friday of M+1). Where ALFRED vintages are
  available, use the vintage as-of T instead of the lag heuristic.
- Headlines: a per-episode pack of real, dated archival headlines with
  publish date ≤ T, assembled once and content-hash-frozen; reruns use
  the frozen pack.
- Bar-enforced: a harness test asserts every datum's publication date
  ≤ T for every episode — lookahead is a test failure, not a code-review
  hope.

**The honest limit — model memory**: the LLM was trained on history and
may simply *remember* what followed T. This cannot be fully eliminated.
Mitigations, all mandatory: (a) deterministic date-shifting and
instrument pseudonymization in the presented snapshot (mapping stored
for resolution); (b) every backtest row and every summary carries a
non-removable caveat marker (grep-bar: summaries refuse to render
without it); (c) backtest calibration is treated as a diagnostic
lower-bound signal for the *pipeline mechanics*, never comparable 1:1
with live calibration — which is precisely why the tracks never mix.

**Instant resolution**: the existing `resolve_prediction` code path
(code decides, never model-asserted) evaluated against post-T known
data, writing only to the backtest ledger.

**No-tuning loop, structurally visible**: results are one cohort per
(episode list, code version); any change to prompts/mechanisms/
thresholds requires a new cohort_id and new sign-off to re-run. Silent
iterate-until-pretty is impossible without leaving a paper trail.

**Deterministic gate bars** (all must pass before the track is declared
operational):
- (a) Zero-lookahead test passes for all episodes (publication-date
  assertion, per-episode, in code).
- (b) Track isolation: live calibration outputs byte-identical before
  vs after a full backtest run (golden-file test), and live/backtest
  source-whitelist refusal tests pass.
- (c) Reproducibility: model calls recorded on first run and replayed
  thereafter (store-and-replay), so a cohort is exactly re-derivable;
  OR, if replay is rejected, Task-3-style distribution stability
  (≥4/5 modal rule agreement per episode).
- (d) Caveat-marker grep bars: 0 rendered summaries without the
  contamination caveat; 0 occurrences of backtest rows in any live
  query result (asserted).
- (e) Offline suite green; spend within budget.

**Budget (one-time, not recurring)**: ≤10 DATA calls/episode (frozen
after first assembly), ≤3 MODEL calls/episode → 12 episodes ≈ ≤36 model
calls, single-digit dollars total. Park if exceeded.

**Explicit non-effects**: does not count toward Alpaca's gate; does not
touch the mechanism library; does not adjust any confidence or
threshold; does not run on cron (human-triggered per cohort).

---

## 3. Headline-sourcing task (scoped so the weekly report can go on cron)

**Problem** (from market_engine_trace's own caveat): the weekly regime
report needs fresh real headlines; a static cron arg goes stale and
silently degrades extraction.

**Task spec (RUNNABLE once you approve the feed allowlist):**
- Source: fixed allowlist of free, stable RSS feeds (proposed: Reuters
  Business, AP Business, Yahoo Finance market headlines; final list =
  your call). No scraping beyond RSS, no vendor, 0 model calls for
  sourcing.
- Selection: recency filter (≤7 days), dedupe, top-K (K=3) by
  deterministic keyword-overlap score against the regime vocabulary —
  code, not model.
- Provenance: chosen headlines written into the report header with
  source URL + fetch timestamp.
- Degradation: zero qualifying headlines → report runs numeric-only
  (existing correct-silence path), never a stale or fabricated
  headline.
- **Bars**: (a) fixture test — recorded RSS payloads produce
  deterministic top-K with no network; (b) live run writes provenance
  lines; (c) zero-headline day asserted to produce numeric-only mode;
  (d) suite green. Budget: ≤3 fetches/run, $0 model.
- After merge, the weekly cron line becomes fully unattended:
  `generate_weekly_regime_report.py --headlines-from-feeds` +
  `record_baselines.py`, Mondays 08:00.

**Decision needed**: approve the feed allowlist (or name preferred
sources).

---

## 4. Task 3b v2 ambiguity gate — attempted, blocked in sandbox, handed off

Ran `scripts/mechanism_extraction_reliability_gate_v2.py` from the
Cowork sandbox 3× (with socksio fix and proxy variants):
`anthropic.APIConnectionError` — this sandbox's egress does not reach
api.anthropic.com (same limitation recorded 2026-07-17). The gate must
run on the Mac:

    cd ~/intent-engine && .venv/bin/python scripts/mechanism_extraction_reliability_gate_v2.py

Cost ≤40 haiku calls (budget ceiling inherited from Task 3). Per the
script's own scope note, its outcome does NOT auto-unpark Task 3 — you
review the result against the park. Attempt logs:
`logs/task3b_gate_v2_run{2,3}.log`.

---

## Decision checklist (what you're approving/rejecting)

1. Daily cadence: instrument allowlist, cap 5/day, $7/mo ceiling,
   numeric-only start — approve to implement.
2. Backtest track: **A-M3 amendment text above** + episode-list
   pre-registration + the bars — approve BOTH before any code.
3. Headline sourcing: feed allowlist — approve to implement, then
   weekly report goes on cron.
4. Task 3b gate: run the one-liner on the Mac; paste or point me at the
   log and I'll record the verdict in overnight_trace.md.
