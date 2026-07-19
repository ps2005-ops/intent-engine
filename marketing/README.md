# Marketing-agent workspace

*Stood up 2026-07-19 per docs/AGENTS.md §3 (marketing agent) under the
business-building-phase instruction. AGENTS.md defines this agent with no
dedicated repo — it "operates against whichever project needs
marketing/content work" and must not touch intent-engine core src — so
the workspace lives here as a draft-content directory. If you'd rather it
be a sibling repo, say so and it moves wholesale (nothing here imports
engine code).*

## Purpose (from AGENTS.md, inherited verbatim)

Content strategy, copywriting, and — once flipped by the founder —
scheduled social posting through the single human-approved tool
(**Publer**, decided 2026-07-17). Drafts and recommends; a human approves;
one audited tool publishes.

## Walls (all inherited, none new, none relaxed)

1. **NOTHING PUBLISHES, NOTHING SENDS** without explicit per-item founder
   approval. The Publer pipeline ships in DRY-RUN mode and refuses real
   mode until the founder creates the flag file `PUBLISHING_ENABLED` in
   this directory (see publer_pipeline.py — the check is code, not
   convention). No unsupervised posting, ever; MoneyPrinterTurbo-style
   autonomous publishing is permanently excluded.
2. **CLAIM-TRACING RULE (business phase, hard wall)**: every capability or
   performance claim in every draft carries an inline trace `[T:n]` to a
   gate-passed capability or a ledgered fact (trace table at the bottom of
   each draft). **No predictive-accuracy claims exist anywhere and none
   may be added until ≥30 live resolved predictions per source AND the
   founder's calibration review** — at which point the claims still only
   say what the ledger says.
3. **Credentials**: `PUBLER_API_KEY` is read at runtime from
   `intent-engine/.env` — never copied into this directory, never printed,
   never logged (docs/TOOLS.md records the decision).
4. No sentiment feeds as signals. No vendor accounts, no OAuth flows
   created by the agent. No touching `src/` or the job-application
   submission path.

## Layout

    README.md                      — this file (walls first, per instruction)
    publer_pipeline.py             — DRY-RUN Publer client (gated as above)
    drafts/landing_page_copy.md    — deliverable (a), DRAFT
    drafts/sample_structural_analysis_template.md — deliverable (b), DRAFT
    drafts/weekly_regime_content_formats.md — deliverable (c), DRAFT
    outreach/                      — workstream-5 cold-outreach package, DRAFTS
    PUBLISHING_ENABLED             — DOES NOT EXIST until the founder creates it

## Approval state

Every file under drafts/ and outreach/ is DRAFT-ONLY awaiting per-item
founder approval. Nothing has been posted, scheduled, or sent.
