# Per-message approval checklist — one row = one tap to approve a send

*Fill one block per prospect. You approve by replying "approve <id>" (or
editing `approved` to your stamp). On approval, the message is logged to
ledger.jsonl as status="approved", and only THEN may it move to
status="sent" (which is a human act on the Mac — the dry-run/real wall
from the job-application workflow applies identically; nothing sends from
the sandbox, ever).*

## Block template

    outreach_id:   2026-07-2X-<company>-<firstname>
    variant:       V1-DM | V2-email-subjectA | V2-email-subjectB | V3-followup
    recipient:     [name], [title] @ [company]  (real research: <source>)
    decision-hook: <the specific decision this founder is weighing, in your words>
    channel:       dm | email
    ---- message preview (exact text that would send) ----
    <the filled V1/V2/V3 text with [name]/[company]/[decision-hook] resolved>
    ---- claim-trace audit (must be all-yes to be approvable) ----
    [ ] every capability claim maps to T:1–T:6 (no new/unlisted claim)
    [ ] zero predictive-accuracy claims; the only performance line is the disclaimer
    [ ] personalization fields are real (no invented facts about the recipient)
    [ ] one-follow-up rule respected (V3 only if V1/V2 already sent & unanswered)
    ---- founder decision ----
    approved:      <null until you stamp it, e.g. "founder 2026-07-2X"> 
    notes:         <optional>

## How it flows

1. Agent fills a block from real research (never invents recipient facts).
2. You review; the four audit checkboxes must all be yes.
3. You stamp `approved` → agent appends a status="approved" row to
   ledger.jsonl.
4. Sending is a separate human step on the Mac. The agent never sends and
   never creates a status="sent" row without a prior approved row +
   non-null `approved_by` (tracking_ledger_schema.md, invariant #2).
