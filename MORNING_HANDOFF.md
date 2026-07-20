# MORNING HANDOFF — loop 9 (2026-07-20) — T006 DONE, T009 live harvested, base at v1.1

*Suite at close: **668 passed, 0 failed, 9 deselected (live/networked)**,
EXIT=0 explicitly checked before every commit. Loop-9 commits: `ab26eb5`
(T006 → DONE), `26c575d` (T009 harvest + generator v1.1) + this handoff.
Walls held: prompts/enum/library untouched; 0 sandbox model calls; the
loop's live calls were both founder-run (T006 fixture ~2-3 calls incl.
one in-budget retry; T009 89 calls ≈ $1.78). Training remains gated: the
"training" extracted this loop is the findings below, not weights.*

## What closed this loop

1. **T006 → DONE.** Your fixture run recorded 3 predictions; I verified
   them by direct DB read: all source="premortem", p ∈ {0.72, 0.65,
   0.58}, resolve_by strictly future, claims resolvable (pipeline count /
   runway months / roadmap-iteration presence). Append-only held. The
   328-char length retry you flagged is recorded in the trace as a
   watch-item (in-budget, auto-recovered).
2. **T009 live leg harvested.** Headline: **condition recall 1.00** — on
   89 fully fictional worlds the extraction leg never missed a planted
   causal symptom; 68/69 singles and 12/12 mixed worlds recovered.
   The negative finding was one systematic artifact: my v1.0 opener
   ("its principal competitor is {rival}") baited
   `few_dominant_competitors` 67 times, costing precision (0.68), 5/8
   control silences, and the lone miss. That was the GENERATOR's fault
   first — fixed as **base v1.1**: concentrated phrasing only where the
   condition is planted; broad-field counter-evidence phrasing everywhere
   else. v1.0's record is preserved in the live report with analysis.

## LEDGER GROWTH SNAPSHOT (2026-07-20)

- **Total: 12** (7 market, 3 premortem, 2 baseline) · resolved: 0 ·
  gate: ≥30 LIVE resolved **per source**.
- The premortem source is now live and accruing whenever you run audits
  with `--record-predictions`; its resolve window opens 2026-11-20.
- Market/baseline accrual starts with the cron job's first fire (Monday
  18:30 ET if you installed paste 1 — I can't see your crontab from the
  sandbox; Monday's spend-log row will be the evidence either way).

## MY MORNING LIST

1. **(If not already done) install the cron line** — paste 1 from
   yesterday; idempotent.
2. **DONE — v1.1 re-run happened** (controls 8/8 clean, precision 0.907,
   recall 1.000 again; your overwrite + stale-template flags both fixed —
   runs now archive append-only with a cross-run history table). OPEN per
   your own point: one clean run doesn't bound the control-hallucination
   rate on a non-deterministic leg — 2-3 more runs (~$1.78 each, same
   command, any day) would. No urgency; each run auto-appends to the
   history.
3. Nothing else is blocked on you. Next build item is Phase 2 (deliberate
   weekly sector spanning) — recommendation unchanged: let a week of live
   v2 ledger data accrue first, then decide whether the mechanical 29-day
   rotation needs the weekly guarantee.

## AMBIGUITIES (parked with recommendations)

1. **Bridge claim-length cap (300)**: the live run tripped it once and
   recovered. *Recommendation: leave the cap (it forces crisp claims);
   revisit only if the retry recurs — each retry costs a call.*
2. **v1.1 live re-run cost**: ≈$1.78 per run. *Recommendation: run once
   now for the clean baseline, then only after future base versions.*
3. **Cron status unknown to me** (sandbox can't read your crontab).
   *Recommendation: nothing — Monday's log answers it.*

*Recurring note: densification's value is DENSITY and BREADTH, not being
right; the synthetic eval's value is DIAGNOSIS, not a claim. Nothing here
tunes, filters, or cherry-picks; the ledger and reports record what the
engine honestly produces.*
