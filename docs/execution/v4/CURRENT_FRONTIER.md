# CURRENT FRONTIER

Resume pointer. A new session needs only this file plus AGENT_PROTOCOL.md to
continue; everything here is recomputable from TASK_GRAPH.yaml.

    python3 docs/execution/v4/frontier.py

Do not trust this file over the script. If they disagree, the script is right
and this file is stale.

## As of 2026-08-09 (end of the bootstrap + PROGRAM A run)

    37 nodes   COMPLETE=11   READY=5   WAITING_DEPENDENCY=17   BLOCKED_DATA=4

    p1  K-CYC-002   Verify source_preference and research_decisions reach a report
    p2  J-BRK-001   Break proofs for the new research-observability guards
    p3  D-REP-001   Vintage wall for replay                     (unblocks 5)
    p3  G-THE-001   Thesis revision history                     (unblocks 4)
    p3  C-MET-001   EconomicMethod registry                     (unblocks 2)
    p3  E-DEM-001   Targeted demand-variable extraction         (unblocks 1)
    p3  I-ACC-001   Learning acceleration from KnowledgeEffect  (unblocks 1)
    p3  J-ADV-001   Adversarial suite extension

`frontier.py` ranks by dependencies only and does NOT read `minimum_data`.
B-POL-002, B-HACK-001 and B-VOI-002 became READY when A-RD-008 completed and
were set to BLOCKED_DATA by hand, because the prospective sample is 2 against a
gate of 100. Check `minimum_data` against BLOCKERS.yaml before claiming a node.

## What PROGRAM A established

The engine now writes the choice BEFORE the call. A live night cycle against
the production root wrote 2 decisions and 2 outcomes, each carrying the full
menu — including `partnership_release` marked ineligible with the reason
`cadence 3d; not due today` — and the forgone option.

## What it did NOT establish

1. **No empty-handed row has occurred in production.** Both live outcomes were
   SUCCESS. `NO_RESULT` and `FAILED` — the rows this whole module exists to
   preserve — are unit-tested across all six statuses and have never been
   observed live. Until one appears, the claim that the log is unbiased is
   architectural, not empirical.

2. **Two projections reached the report empty.** `source_preference` and
   `research_decisions` were `{}` in `2026-08-09_night.json`, because the run
   started before `431538b`. K-CYC-002.

3. **The sample is rate-bound.** ~2 decisions per night; the 100 gate is ~50
   cycles away. Do not raise it by logging a decision per (family, subject) —
   the cycle chooses families, not subjects, and those rows would be choices
   nobody made.

## Live findings a resuming session must not re-derive

1. **VOIPolicy is a constant, not an estimate.** Measured identical to
   `FixedPolicy(regulatory_filing)` on all six figures. Independence is 1.0 for
   both top families, so the order's own rationale does not separate them;
   duplication does, 0.75 vs 0.027. The order was deliberately not flipped.

2. **The market venv is the Founder venv.** With `PYTHONPATH` unset,
   `intent_engine` resolves to `/Users/prathamsharma/intent-engine/src`, which
   has no `market` subpackage. Any subprocess in a test must be handed the
   source root explicitly.

3. **The deployed runtime is behind.** launchd runs from
   `/Users/prathamsharma/intent-engine-market`, whose checkout is detached at
   `66c4a15`. `v4b/market` is at `431538b`. The scheduled cycles are therefore
   NOT running this code. Moving the live checkout is a deployment decision and
   was deliberately left to the owner.

## Next action

Run `frontier.py` and take the top node. K-CYC-002 needs one cycle at
`>= 431538b`; it is cheap and it closes the last open claim from this run.
