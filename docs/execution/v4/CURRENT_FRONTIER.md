# CURRENT FRONTIER

Resume pointer. A new session needs only this file plus AGENT_PROTOCOL.md.

    python3 docs/execution/v4/metrics.py --write   # remeasure the data gates
    python3 docs/execution/v4/frontier.py          # what is runnable
    python3 docs/execution/v4/frontier.py --check  # fails if drift reappeared

Do not trust this file over the script. If they disagree, the script is right.

## As of 2026-08-09, end of the frontier-exhaustion run

    42 nodes   COMPLETE=19   READY=8   WAITING_DEPENDENCY=12   BLOCKED_DATA=3

    p2  G-THE-003   EVALUATE: a second cycle produces a real transition
    p3  C-MET-002   MethodAssumptionCheck ledger              (unblocks 1)
    p3  E-DEM-001   Targeted demand-variable extraction       (unblocks 1)
    p3  I-ACC-001   Learning acceleration from KnowledgeEffect (unblocks 1)
    p3  C-MET-004   INSTRUMENT: MethodPerformance accumulates
    p3  J-ADV-001   Adversarial suite extension
    p4  D-REP-002   Historical thesis replay                  (unblocks 4)
    p4  H-CEO-001   CEO Q&A from canonical records            (unblocks 3)

V4 IS NOT CLOSED. Eight executable nodes remain and none is blocked.

Three of the eight exist because of the maturity audit, not because new
capability was scoped: A-RD-009 (done), C-MET-004 and G-THE-003. The audit
greps production importers for every COMPLETE capability whose acceptance
implies runtime use. Run it again before believing any COMPLETE:

    for m in <module>; do grep -rl "import $m" --include="*.py" src/ ; done

`vintage` and `economic_method` still have zero production importers.
`vintage` is fine — its consumer is D-REP-002. `economic_method` is C-MET-004.

## What the live cycle proved, and what it did not

Thesis revisions are LIVE: 7 written and held at runtime_git_sha 58566f9,
with 7 snapshots persisted. But `loaded` was 0 and `compared` was 0, because
it was the first cycle to write snapshots — every revision is CREATED, and
`classify()` plus the effect-attribution rule have never run on a real
movement. G-THE-003 is exactly that gap and needs only a second cycle.

Prospective decisions moved 4 -> 6 on their own during this run.

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
