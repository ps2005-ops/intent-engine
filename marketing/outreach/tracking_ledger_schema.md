# Cold-outreach tracking ledger — schema (append-only) — DRAFT

*Same append-only discipline as every ledger in this project: rows are
never mutated or deleted; a state change is a NEW row with the same
outreach_id; reads collapse to the latest row per id (exactly
prediction_ledger's convention). Storage: `marketing/outreach/ledger.jsonl`
(file does not exist until the first founder-approved send is logged —
creating rows for unsent drafts is forbidden except status="drafted").*

## Row schema (JSONL, one object per line)

| field | type | notes |
|---|---|---|
| outreach_id | str | stable id per prospect+thread, e.g. "2026-07-21-acme-jane" |
| logged_at | ISO timestamp | when THIS row was appended |
| status | enum | drafted → approved → sent → replied → converted / declined / no_response_closed |
| channel | enum | dm / email / followup |
| variant | str | e.g. "v2-email-subjectA" (message-variant A/B tracking) |
| prospect | str | name/company (real research only, no scraped bulk lists) |
| approved_by | str or null | REQUIRED non-null before any status="sent" row — per-message founder approval stamp |
| sent_at | ISO or null | set on status="sent" |
| reply_summary | str or null | 1-line, factual |
| converted_to | str or null | "analysis-delivered" / "call" / "testimonial" |
| notes | str | free text |

## Invariants (enforced by whatever tool writes rows, and checkable by a 10-line audit script)

1. Append-only: no row edits, no deletions.
2. No status="sent" row without a prior status="approved" row AND a
   non-null approved_by — the job-application workflow's dry-run/real
   wall, identically.
3. status="drafted" rows carry sent_at=null always.
4. Conversion metrics are computed by code over the file — never
   hand-tallied into a summary that can drift from the rows.

## Metrics read (computed, not stored)

sent → reply rate, reply → analysis-delivered rate, per-variant splits.
No metric is quoted externally without the founder seeing the raw rows.
