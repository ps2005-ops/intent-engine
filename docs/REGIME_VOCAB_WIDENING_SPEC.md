# T008 — REGIME_VOCAB widening — MERGED

*Status: MERGED 2026-07-19 (founder approved the spec; overnight loop 8).
All 5 bars asserted as tests in tests/test_headline_feed.py; no term
dropped (bar-c controls stayed at 0). Spec preserved below as written.*

## Motivation (the real finding it fixes)

During the AP-feed decision-prep, real NPR headlines showed the headline
scorer missing clearly-markets items: "SpaceX **IPO** … **Stock** gains
19%" and "Paramount-Warner **merger**" both scored 0, because
`core/headline_feed.REGIME_VOCAB` has "stocks" (plural) but not
"stock"/"ipo"/"merger". Widening the vocab makes the recency+score filter
surface these instead of dropping them.

## Change

Add to `REGIME_VOCAB` (in `core/headline_feed.py`): **ipo, merger,
acquisition, stock, buyback, guidance**. Additive only — no existing term
removed, no scoring logic changed (still a deterministic word-overlap
count, still 0 model calls).

## Deterministic bars (all offline)

- (a) **Additive**: every current `REGIME_VOCAB` term still present; the 6
  new terms present; length increased by exactly 6.
- (b) **Real-miss fix**: the three real NPR titles that scored 0
  ("SpaceX IPO … Stock gains 19%", "Paramount-Warner merger …", and one
  acquisition headline) now score >= 1 — asserted directly.
- (c) **No false-positive inflation**: a fixed set of clearly-NON-markets
  control titles (e.g. "Celebrity opens new restaurant", "Cat wins
  pageant") still score 0 — the new terms don't over-trigger.
- (d) **Determinism / no logic change**: `score_title` is unchanged;
  scoring a title twice yields the same result; the selection pipeline's
  existing tests still pass unchanged.
- (e) **Suite green**, explicit exit-code check before commit.

## Budget / walls

0 live calls, 0 fetches. Additive data change to a shared tested surface —
NOT the frozen TriggerCondition enum (that is a different, separately-gated
surface; this is the headline vocab). One commit on your approval.

## Park conditions

- If any new term measurably inflates false positives on the control set
  (bar c fails) → drop that term, keep the rest, report which.
- No scope creep into scoring-logic changes — this is a term-list
  addition only.

**Awaiting your approval to merge.**
