# CURRENT FRONTIER

Resume pointer. A new session needs only this file plus AGENT_PROTOCOL.md to
continue; everything here is recomputable from TASK_GRAPH.yaml.

    python3 docs/execution/v4/frontier.py

Do not trust this file over the script. If they disagree, the script is right
and this file is stale.

## As of 2026-08-09

    36 nodes   READY=7   WAITING_DEPENDENCY=28   BLOCKED_DATA=1

    p1  A-RD-001   unblocks 17   ResearchDecision written BEFORE the call
    p1  K-CYC-001  unblocks  0   Verify V4 projections reach a run report
    p2  B-VOI-001  unblocks  4   Diagnose the VOI filing bias by measurement
    p3  D-REP-001  unblocks  5   Vintage wall for replay
    p3  G-THE-001  unblocks  4   Thesis revision history
    p3  C-MET-001  unblocks  2   EconomicMethod registry
    p3  E-DEM-001  unblocks  1   Targeted demand-variable extraction

## Why A-RD-001 is first

It is not the most interesting node. It unblocks 17 of 36 — the whole of
PROGRAM B and the reward half of PROGRAM I depend on it.

The engine can now attribute evidence to knowledge change (session 3). It
cannot yet attribute a knowledge change back to the *choice* that sought the
evidence. The research log is rebuilt from evidence that survived, so an action
that returned nothing leaves no trace, and every rate computed from it is
biased toward success. Logging the decision before the call is the only fix.

## Live findings a resuming session must not re-derive

1. **No cycle has run with the V4 projections.** `report.py` gained them at
   `3eb24d2` (2026-08-08 21:31); the last night report was written 20:28. The
   session-3 `reconstructed: 0` figure came from an in-process probe. Tracked
   as K-CYC-001.

2. **VOIPolicy is a constant, not a computation.** A hardcoded preference
   order with `REGULATORY_FILING` first. And `evaluate_offline` offers all five
   families on every record regardless of what was eligible. Falsifiable
   prediction under B-VOI-001: VOIPolicy scores identically to
   `FixedPolicy(regulatory_filing)`.

3. **The market venv is the Founder venv.** `PYTHONPATH=src` is mandatory for
   any probe or test run in a worktree.

## Next action

Execute A-RD-001. Then recompute the frontier — do not assume A-RD-002 is next.
