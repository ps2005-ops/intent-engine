# BATCH 21 — PRE100 completion run

Start `582ccf0` → end `da6881d` (deployed, live-verified).
Market `9b01ff1`, production `cfd4c3b` untouched.

## ACQUISITION_PRE100_FROZEN = TRUE
Reopened only for D3/D7 as the freeze permits, closed at ~12% of the run, and
not touched again.

## D3 / D7 — DIAGNOSED, root cause is NOT a pipeline defect
Measured directly: `caterpillar.com` → **HTTP 403** on apex and www;
`cloudflare.com` → 301. Caterpillar's zero was a blocked retrieval. No
retrieval matrix was re-run.

## D6 — FIXED AT THE PRODUCER, live-verified
The brief opened "what has published is not enough". Normalised once in
`compose_decision`, the single decision object every surface renders, rather
than patching the sentence. Live on `da6881d`: "what this company has
published is not enough".
OPEN: `company_name` is still empty at that producer on this path. The guard
means it can never be customer-visible again, but the emptiness is real.

## D7 — SURFACE FIXED, live-verified in part
The absent-`company_owned` consequence read "Everything here is the company
describing itself" — a description of the OPPOSITE situation. Every string in
that table renders only on ABSENCE, so it had been wrong since it was written
and stayed invisible until a run retrieved nothing. Now: "We could not read
anything the company publishes about itself."
The blocked-access explanation is built and unit-proven but did NOT render on
this live run, because the run recorded no retrieval failures at all.

## D8 — NEW, SEV2, found on the same live page
The brief shows "WHAT COULD ACTUALLY BE READ / SEC 10-K (...)" while "WHAT
THIS WAS BUILT FROM" lists "Filings and investor material — none". Two
sections of one page contradict each other: `source_class_coverage` is empty
while documents exist. This also explains why no failures were recorded — the
run has documents but no per-class accounting reaching the report.
NEXT: this is the highest-value defect on the board and it is a seam, not
acquisition. Fix `source_class_coverage` population, not retrieval.

## ECONOMIC HISTORY — BUILT
`historical_playback` had two consumers and NO producer; both the X-Ray and
the deck carried hardcoded paragraphs explaining its absence, already drifted
apart. Now `strategic_intelligence/economic_history.py`:
- three states, only one of which is a replay
- the vintage wall filters on `retrieved_at` (when WE observed it), never on a
  date printed inside the document
- an undated observation is EXCLUDED — one missing timestamp must not reopen
  the future
- blocked case carries months held / months required / clearing date
- outcome and mechanism scored on separate axes (right-for-the-wrong-reason
  is kept distinct from skill)
Chain proven producer → report → decision → X-Ray → deck, with negative
controls that an absent assessment invents no state.

## NOT BUILT
Hydration, second iteration, X-Ray/Full Analysis rewrite, 13-slide deck
population, CEO Q&A exercise, Personal AI integration, live journeys 3-9,
acceptance, hostile buyer, security, zero-Anthropic.

NOTE on the deck: it already contains 13 `add()` calls. It rendered 7 because
`_slide()` correctly drops slides with nothing behind them. The 13-slide
target is a STATE problem, not a deck problem.
