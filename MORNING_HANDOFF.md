# MORNING HANDOFF — overnight loop 7 (2026-07-22) — backlog cleared + densification kickoff

*Suite at close: **635 passed, 0 failed, 7 deselected (live)**. 8 commits
(`4c5c27c` → `f9f31591`) + this handoff. Walls held: no publishing/sending/
crontab/vendor/OAuth/sandbox-live-calls; A-M3 untouched, backtest HELD,
enum frozen, prompts frozen. Process guard honored — every commit gated on
an explicit suite exit-code check (EXIT=0). Spend: 0 live model calls;
4 web_fetches (LTCM citation verify + batch-3 sources).*

## Backlog clearance — all 8 items, per-item status

1. **T005 → DONE** (`4c5c27c`). Both live bars PASS (your outputs pasted
   into `overnight_trace.md`); ROADMAP flipped.
2. **LTCM citation swapped** — the 404'd `/276/hedgefund.pdf` → your
   `/236/hedgfund.pdf`; sandbox web_fetch confirmed ~140KB real Treasury
   PDF (reachable). `citation_check.sh` updated for the authoritative Mac
   run; sechistorical.org mirror added.
3. **Batch-2 MERGED as-is** (`9ef8528`) — +2 mechanisms +2 enrichments →
   **22 entries**; bar-(e) prompt byte-identity PASS; `currency_peg`
   stays parked; suite exit-checked.
4. **Enum candidates** — DEFERRED (no action), now complete at 5 after
   batch 3 (see below).
5. **Task 5 (T006) → runnable queue** (`916b1b1`).
6. **AP feed → NPR Business** (`7be77d4`) — Reuters+AP dropped
   (web-fetch-blocked), NPR added; allowlist + test updated.
7. **REGIME_VOCAB widening → SPEC ONLY** (`f80fcba`, doc T008) — awaiting
   your approval before merge.
8. **Marketing + outreach → APPROVED AS DRAFTS** (`f80fcba`) — recorded in
   `marketing/README`; PUBLISHING_ENABLED uncreated, per-message send wall
   stands (approval does not move anything past dry-run).

## Densification plan

### Phase 1 — cadence-v2 proposal (STAGED, awaiting approval)
`docs/CADENCE_V2_PROPOSAL.md` (`f80fcba`). Proposes: instrument allowlist
13 → ~30 (9 more sector ETFs + broad/intl/credit ETFs + 7 more FRED macro
series, all deterministic + pydantic-validated); daily cap **5 → 8** (fills
the 4 horizon buckets at 2 each); **ceiling stays $7** (breadth adds $0
data calls, not model calls — model estimate ~$1.68/mo). All quality guards
unchanged. **Needs three explicit approvals: allowlist, cap, ceiling.** Code
staged, not built.

### Still-parked items finished as gates cleared
- **Library batch 3 (episodes 9-12, FINAL)** — staged at your gate
  (`f9f31591`), unblocked by the batch-2 merge. Honest finding: dot-com
  and GFC are already well-covered; batch 3 = **1 new** (COVID
  `exogenous_activity_halt`, collision-flagged) + **2 enrichments**
  (2021-22 inflation, 2022 hiking) + **1 parked** (GFC
  `securitized_credit_opacity` → enum candidate #5). `mechanisms.json`
  untouched; merge waits for your verdict + 2 PENDING-MAC citations.
  **This completes the 12-episode curriculum.**

## LEDGER GROWTH SNAPSHOT (2026-07-22)

- **Total predictions: 9** (7 market, 2 baseline) · **resolved: 0** ·
  toward the ≥30-resolved-per-source gate.
- By instrument: SPY ×6 + 3 macro. By horizon: resolve_by window
  **2026-08-31 → 2026-10-16**.
- **First resolution: 2026-08-31** (nothing resolvable before then).
- **The gap to ≥30 is what densification closes** — but daily generation
  runs on the Mac (the sandbox has no Anthropic egress), so the ledger
  only grows once cadence-v2 is approved AND the daily job runs on your
  machine. That dependency is the single biggest lever on calibration
  timing.

## MY MORNING LIST (in order)

1. **Approve cadence-v2's three numbers** (allowlist / cap=8 / ceiling=$7)
   — this is the densification engine; nothing accrues without it.
2. **Batch-3 verdict** (`docs/library_batch3_review_sheet.md`) + run
   `sh citation_check.sh` (now includes batch-3's NBER/BLS/Fed URLs — the
   2 PENDING-MAC ones must show 200 before merge). On approval: merge →
   23 entries, and I complete `MECHANISM_LIBRARY_STATE.md` to 12/12.
3. **The batched enum decision** — the candidate list is now complete at 5
   (`docs/library_batch3_review_sheet.md` lists all with what each
   unlocks). Any widening = your sign-off + a full Task 3 gate rerun.
4. **REGIME_VOCAB widening** (T008) — approve to merge, or leave.
5. **Start the daily prediction job on the Mac** once cadence-v2 is live —
   the only way the ledger grows toward the gate.

## AMBIGUITIES (parked with recommendations, not guessed)

1. **Cadence-v2 ceiling**: I recommend keeping $7 (breadth is data calls =
   $0, not model calls). *If you want headroom for a future cap>8 or an
   LLM-prose feature, name a number; otherwise $7 stands.*
2. **exogenous_activity_halt collision** (COVID, batch 3): same class you
   accepted twice. *Recommendation: accept (distinct causal shape); flagged
   for your explicit call.*
3. **2 batch-3 citations PENDING-MAC** (BLS CPI, Fed open-market). *In
   citation_check.sh; run on the Mac before merging batch 3.*
4. **Phase 3 (synthetic-world reasoning test)** is scoped as spec-only/low-
   priority in the plan; I did NOT scope it this loop (Phase 1 + backlog
   filled the loop). *Recommendation: I scope it next loop unless you'd
   rather I prioritize building cadence-v2 the moment you approve it.*

## Free-time use (per whitelist)

Loop was full with the 8-item clearance + Phase-1 proposal + batch-3
research; no spare-time work beyond trace/handoff accuracy. Not touched:
enum/prompt edits, publishing past dry-run, backtest-of-LLM-judgment,
company-fundamental engine, accuracy claims.
