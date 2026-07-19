# MORNING HANDOFF — overnight loop 4 (2026-07-21/22)

*Suite at close: **627 passed, 0 failed, 7 deselected (live)**. 3 commits
(`e137690` → `22f9141`). Walls held: no publishing, no sending, no crontab
writes, no vendor accounts, no OAuth, no live Anthropic calls from
sandbox; A-M3 untouched, backtest HELD, enum frozen, prompts frozen.
Process guard honored: every commit gated on an explicit suite exit-code
check. Spend loop 4: 0 fetches, 0 live model calls.*

## Were A/B/C/D filled-and-executed, or parked? (per-field, as requested)

**All four PARKED — unfilled a fourth time** (arrived as menus like
`"approved" OR feedback`, no selection). Per your explicit rule this loop
("a selection, not a menu; menu-style = parked a fourth time") I parked
rather than guessed:

- **A (T005 live bars)** — PARKED. T005 stays LIVE-BARS-PENDING-HUMAN;
  disk shows still no t005-live rows / no new run logs.
- **B (marketing drafts)** — PARKED. Stay DRAFT-pending-approval.
- **C (outreach package)** — PARKED. Stays DRAFT-pending-approval.
- **D (citation_check.sh)** — PARKED. Batch-2 citations unverified →
  **batch-2 NOT merged** (the rule requires verdict AND D=200s; neither).
- **Standing picks** (batch-2 verdict, Task 5, AP feed, vocab) — all
  PARKED (unfilled menus). Allowlist, enum, prompts untouched;
  `mechanisms.json` still 20 entries.

## Workstream states

### 1. Execute filled fields
- **State**: parked — nothing filled. No commits.
- **Next human action**: fill A/B/C/D + standing picks with bare selections.

### 2. Library batch 3 (final batch, episodes 9–12)
- **State**: NOT started — gated on the batch-2 verdict, which was
  unfilled. Curriculum stays **8/12 studied**.
- **Next human action**: give the batch-2 verdict; then batch 3 runs and
  the library inventory completes to 12/12.

### 3. Mechanism explanation-depth spec (T007) — DELIVERED
- **State**: DONE — `docs/MECHANISM_EXPLANATION_DEPTH_SPEC.md`, SPEC ONLY.
  Notable finding: it's a **deterministic render of existing data (0 live
  calls)**, not a new model call — so if approved it's fully buildable and
  testable in-sandbox, unlike T005. 6 offline bars incl. no-prediction
  grep walls.
- **Commits**: `0d12761`.
- **Next human action**: approve/amend → runnable queue (build could then
  finish in one sandbox loop, no Mac step).

### 4. Positioning memo — DELIVERED
- **State**: DONE — `docs/POSITIONING.md`. Thesis: the moat is verified,
  code-graded forward calibration + transparent method, NOT an accuracy
  number; why faking a number before Sep calibration is fatal; what's
  sellable now.
- **Commits**: `22f9141`.
- **Next human action**: read — decision-support for the go-to-market
  stance. Nothing to approve.

### 5. Task 5 implementation (T006)
- **State**: skipped — spec unapproved (unfilled). Not implemented.
- **Next human action**: approve/amend `docs/TASK5_WIRING_SPEC_PROPOSAL.md`.

## MY MORNING LIST (in order)

1. **Run the two Mac commands** — they *are* the A and D answers, so this
   is the single highest-leverage action:
   - `cd ~/intent-engine` + the two one-liners in `T005_LIVE_RUNS.md` → A.
   - `cd ~/intent-engine && sh citation_check.sh` → D (LTCM + Japan must
     show 200 before batch-2 can merge).
2. **Send bare selections** for B, C, and the four standing picks
   (recommended, if you concur: B/C "approved"; batch-2 "approve as-is";
   Task 5 "approve"; AP "replace with NPR"; vocab "yes").
3. **Read (no approval needed)**: `docs/POSITIONING.md` and
   `docs/MECHANISM_EXPLANATION_DEPTH_SPEC.md` — tonight's deliverables.
4. Once the batch-2 verdict lands, batch 3 runs and completes the
   12-episode curriculum + the library inventory.

## AMBIGUITIES (parked with recommendations, not guessed)

1. **Four nights of unfilled brackets — this is now the whole bottleneck.**
   Every build/merge/send item has queued behind it. I have not guessed
   any of them because each guards a real wall (data-file merge, allowlist
   change, code-into-queue, external sends). *Recommendation, unchanged and
   now urgent: run the two Mac commands (they auto-fill A and D) and send
   six one-word answers. That single reply unblocks ~everything at once.*
2. **T007 is the cheapest win in the queue.** Unlike every other pending
   build, it needs no Mac step and no live budget (deterministic render).
   *Recommendation: if you approve only one thing, approve T007 — it can
   ship end-to-end in the next sandbox loop.*
3. **Batch-2 merge stays double-gated** (verdict + D=200s). Even a "yes"
   verdict can't merge until `citation_check.sh` clears LTCM + Japan.
   *Recommendation: run that script alongside the verdict.*

## Free-time use (per whitelist)

After parking items 1/2/5 and delivering 3/4, remaining time went to the
process-guard exit-code checks and this handoff. Not touched: enum edits,
prompt edits, publishing past dry-run, backtest work, new prediction
engines, batch 3.
