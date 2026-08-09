# CURRENT FRONTIER

Resume pointer. A new session needs only this file plus AGENT_PROTOCOL.md.

    python3 docs/execution/v4/metrics.py --write   # remeasure the data gates
    python3 docs/execution/v4/frontier.py          # what is runnable
    python3 docs/execution/v4/frontier.py --check  # fails if drift reappeared

Do not trust this file over the script. If they disagree, the script is right.

## As of 2026-08-09, end of the executor-repair run

    38 nodes   COMPLETE=16   READY=6   WAITING_DEPENDENCY=13   BLOCKED_DATA=3

    p3  G-THE-001   Thesis revision history                  (unblocks 4)
    p3  C-MET-002   MethodAssumptionCheck ledger             (unblocks 1)
    p3  E-DEM-001   Targeted demand-variable extraction      (unblocks 1)
    p3  I-ACC-001   Learning acceleration from KnowledgeEffect (unblocks 1)
    p3  J-ADV-001   Adversarial suite extension
    p4  D-REP-002   Historical thesis replay                 (unblocks 4)

BLOCKED_DATA, measured rather than asserted:

    B-POL-002   prospective_decisions   4 / 100
    B-HACK-001  prospective_decisions   4 / 100
    B-VOI-002   prospective_decisions   4 / 50

These move to READY on their own when the metric crosses. Do not edit them.

## The executor now enforces its own gates

`frontier.py` evaluates `minimum_data` as `{metric: required}` against
`METRICS.json`, measured from the live ledger with a `measured_at`. A missing
metric blocks — "we looked and there are none" and "we could not look" are
different claims and neither makes a node runnable.

Derived state is **not stored**. READY / WAITING_DEPENDENCY / BLOCKED_DATA are
computed; TASK_GRAPH declares only what a measurement cannot establish and
marks the rest `DERIVED`. `--check` fails if a concrete derivable status
reappears, which is the drift that had TASK_GRAPH and BLOCKERS disagreeing.

## Runtime is aligned

    launchd checkout   f026e96   (was 66c4a15, four commits behind)
    imports resolve    /Users/prathamsharma/intent-engine-market/src
    PAPER              enforced
    production         119d345 untouched, no merge to main

Every cycle report now carries `runtime.runtime_git_sha`, captured at process
start. `runtime_provenance.ran_at_or_after(artifact, sha)` is the release gate:
it returned True for the three commits the last run contained and False for the
one that landed after it started.

## What is still architectural rather than empirical

**No empty-handed research row has ever occurred in production.** All four live
outcomes were SUCCESS. `NO_RESULT` and `FAILED` — the rows a reconstructed log
cannot hold, and the reason the prospective log exists — are unit-tested across
all six statuses and never observed. Do not manufacture one. Until one appears
naturally, "the log is unbiased" is a claim about the architecture.

Rate: ~2 decisions per night cycle. The 100 gate is ~48 cycles out. The
tempting shortcut is a decision per (family, subject), which would give 52 by
morning and every one would be a choice nobody made. The cycle picks families.

## Findings a resuming session must not re-derive

1. **VOIPolicy is a constant, not an estimate.** Identical to
   `FixedPolicy(regulatory_filing)` on all six figures. Independence is 1.0 for
   both top families so its stated rationale cannot separate them; duplication
   does, 0.75 vs 0.027. Not flipped by hand — see B-VOI-001 and §12 of the
   brief. `diagnose_source_preference` reports the gap every cycle.

2. **Persistence is the bar for macro levels.** Walk-forward over 15 real
   series: persistence best on 9, AR1 on 4, drift on 2, and effectively
   unbeaten on the four 520-point series. The 24-point wins are ~16
   out-of-sample predictions and are recorded as suggestive, not promoted.

3. **The market venv is the Founder venv.** With `PYTHONPATH` unset,
   `intent_engine` resolves to the other repository, which has no `market`
   subpackage. Any subprocess in a test must be handed the source root.

## Next action

`G-THE-001`. Then recompute — do not assume the order holds.
