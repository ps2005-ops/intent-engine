# Mechanism library expansion — historical study track — PROPOSAL FOR APPROVAL

*Status: PROPOSED (2026-07-18). No code, no library edits, no searches
consumed until you approve. Workstream 2 of the business-building phase.*

## A-M3 position, stated first

This task is **knowledge acquisition into the library**, which A-M3
explicitly permits and already describes: *"History is INPUT to the
mechanism library only (M3's real historical citations). Evaluation is
FORWARD."* No predictions are made against past data, no model output is
scored against historical outcomes, no rule or threshold is tuned on
what "would have worked." A-M3 needs **no amendment** for this task (in
deliberate contrast to the held backtest track), and this proposal
inherits its wall verbatim: any drift toward "did the library call X
episode" is a park condition, not a stretch goal.

## Current state

`core/data/mechanisms.json`: 17 entries. Schema per entry: mechanism_id,
name, trigger_conditions (subset of the CLOSED 17-value TriggerCondition
enum), causal_chain (ordered human-readable steps), historical_instances
(case / year / real source citation), confidence_tier
(well_documented | plausible | speculative).

## Pre-registered episode list (fixed at approval; additions need new sign-off)

Stratified across the 20th–21st centuries, 12 episodes:

| # | Episode | Why it earns a slot |
|---|---|---|
| 1 | Panic of 1907 | trust-network contagion, lender-of-last-resort absence |
| 2 | 1929–33 Great Depression | debt-deflation spiral, bank-run cascades |
| 3 | 1973–74 oil shock / stagflation | supply-shock propagation into inflation regime |
| 4 | 1980–82 Volcker disinflation | policy-tightening transmission, rate-sensitive demand collapse |
| 5 | 1987 Black Monday | mechanical feedback (portfolio insurance), liquidity vacuum |
| 6 | ~1990 Japan bubble collapse | collateral-value spiral, zombie-balance-sheet stagnation |
| 7 | 1997 Asian financial crisis | currency-peg break contagion, hot-capital reversal |
| 8 | 1998 LTCM | leverage + crowded-trade unwind, counterparty interconnection |
| 9 | 2000–02 dot-com bust | valuation-fundamentals disconnect, capex overbuild digestion |
| 10 | 2007–09 global financial crisis | securitization opacity, funding-run on shadow banking |
| 11 | 2020 COVID crash/recovery | exogenous-stop shock, policy-response reflexivity |
| 12 | 2021–22 inflation / hiking cycle | supply-chain + fiscal impulse, fastest-hike transmission |

## Per-episode protocol

1. **Research** from named sources — primary/official where they exist
   (e.g. FCIC report for #10, Brady Commission for #5, BIS/IMF/NBER
   retrospectives), reputable secondary otherwise. Every fact that enters
   an entry carries its citation.
2. **Draft entries** conforming to the existing schema. New mechanisms
   only when genuinely distinct from the 17 (expected yield: 1–2 new
   mechanisms or new historical_instances on existing mechanisms per
   episode — enriching an existing entry's instance list is a first-class
   outcome, not a failure to find something new).
3. **Closed-enum discipline**: trigger_conditions must be a subset of the
   EXISTING enum. Where an episode genuinely needs a condition that
   doesn't exist (e.g. a currency-peg condition for #7), the condition is
   recorded on a separate NEEDS-APPROVAL list and the mechanism is
   parked — **the enum is prompt-visible, gate-verified surface: widening
   it re-opens the Task 3 gate (full 5x3 rerun) and only you authorize
   that trade.**

## Budget (per approval, tracked per episode in the trace)

- <=10 web searches + <=4 model calls (structuring/drafting) per episode;
- <=12 episodes; estimated total model cost low single-digit dollars;
- hard stop per episode at budget — a half-researched episode parks with
  its notes rather than shipping thin entries.

## Validation bars before any entry merges into the live extraction path

- (a) **Schema bar**: every entry passes `Mechanism(**entry)` pydantic
  validation (automated).
- (b) **Citation bar**: every historical_instance's source URL fetches
  successfully once at validation time, and the fetched title is recorded
  next to the citation in the review sheet (automated fetch, human-read).
  Paywalled-but-real sources get an accessible corroborating citation.
- (c) **Distinctness bar**: no new entry duplicates an existing
  (trigger-set, causal-shape) pair — deterministic trigger-set comparison
  plus your judgment on causal-shape during review.
- (d) **Enum bar**: automated assert that all trigger_conditions are in
  the existing closed set (guarantee that a merge can't silently widen
  prompt surface).
- (e) **Extraction-surface bar**: if (and only if) the enum was NOT
  changed, the extraction prompt is untouched by construction and the
  deterministic matcher's existing tests cover the growth; asserted by a
  test that the prompt string is byte-identical before/after the data
  merge. If the enum WAS changed (only via your approval per above), a
  full Task-3-protocol gate rerun is mandatory before merge.
- (f) **Founder review**: you approve the final entry batch (the review
  sheet: entry + citations + fetched titles) before the single data-file
  commit. Suite green before commit, as always.

## Park conditions

- Sources genuinely conflict on an episode's mechanism → record the
  dispute with both citations, park that episode, no forced entry.
- Episode budget exhausted → park episode with notes.
- Any pressure to evaluate/score the model against an episode's outcome →
  park the whole task and flag (A-M3).

## Marketing wall

Library entries are *documented history with citations*. No downstream
artifact may convert "the library documents 12 major episodes" into a
predictive-skill claim; permissible phrasing is capability-and-method
("structural mechanisms documented from named historical sources, matched
deterministically, with honest silence when nothing matches").
