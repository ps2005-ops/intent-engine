# V4 AGENT PROTOCOL

Permanent execution rules. This file is read FIRST by any session resuming V4,
before TASK_GRAPH.yaml and before any code is touched.

## What this file is for

V4 previously ran from a single natural-language prompt that was simultaneously
specification, planner, scheduler, memory, execution history and release matrix.
That prompt could not be executed: it held ~40 build items and forbade stopping
at any of them, so the only reachable outcome was a large volume of
thinly-verified code plus a report shaped like the requested template.

Planner state now lives in files. The agent's job per turn is small and
mechanical: reconcile, compute frontier, execute one node, validate, record,
commit, recompute.

## Repository identity is a hard invariant

Before ANY mutation, verify and record:

    pwd
    git rev-parse --show-toplevel
    git branch --show-current
    git rev-parse HEAD
    git status --short
    git worktree list

| role   | root                                    | branch       |
|--------|-----------------------------------------|--------------|
| Market | `/Users/prathamsharma/intent-engine-market` | `v4b/market` |
| Founder| `/Users/prathamsharma/intent-engine`     | `v4b/founder`|

`/Users/prathamsharma` is NOT a repository root. It is the user's home
directory and is full of untracked unrelated material.

The canonical checkouts are frequently on the wrong ref (detached, or on
`growth-os`) and frequently dirty with untracked run artifacts. Other agent
sessions hold live worktrees. Two incidents are on record: staged work swept
into another session's commits, and a worktree deleted mid-run.

**Therefore: create a SESSION-OWNED linked worktree from the correct branch and
work only there.** Never adopt another session's uncommitted edits. Never stage
a file you did not write.

Worktree venv trap: a worktree's `.venv` may import `intent_engine` from the
MAIN worktree. Prefix ad-hoc probes with `PYTHONPATH=src`. Pre-commit guards
need `GUARD_PYTHON` set in worktrees; `--no-verify` is never the fix.

## Task status model

Active: `READY` `IN_PROGRESS` `WAITING_DEPENDENCY` `NEEDS_REPAIR`
`NEEDS_MORE_EVIDENCE`

Terminal: `COMPLETE` `INVALIDATED` `BLOCKED_DATA` `BLOCKED_EXTERNAL`
`BLOCKED_OWNER` `NOT_APPLICABLE`

**A `BLOCKED_*` node is terminal for that node only. It leaves the runnable
frontier; it does not stop the program.** A blocked node parks only its
descendants.

## Maturity, not existence

The graph must never encode `implementation exists == capability proven`.
Every capability advances through:

    BUILD -> INSTRUMENT -> COLLECT -> EVALUATE -> CHALLENGE -> PROMOTE

`BUILD` means a class exists. `INSTRUMENT` means the production path calls it.
`COLLECT` means real records accumulated. `EVALUATE` means a measurement was
taken. `CHALLENGE` means an adversary attacked it. `PROMOTE` means it is
allowed to change behaviour.

Two recorded failures make this non-negotiable:

- *a write path is not a write* — the store API existed, the cycle never called
  it, and the retention check read HEALTHY.
- *committed is not deployed* — the producer was green and unrun; the runtime
  pin is the deployment.

A node may only be marked `COMPLETE` with an EXECUTION_LEDGER entry naming a
commit, a test result, and a measured observation from a real run.

## Prohibitions

- Never mark COMPLETE because a Python class exists.
- Never fabricate empirical completion. Never convert UNKNOWN into zero.
- Never convert insufficient data into PASS.
- Never mix PROSPECTIVE and RECONSTRUCTED research records silently.
- Never use retrieval time as occurrence time.
- Never use future information in historical replay.
- Never let an unsupervised discovery become a fact without validation.
- Never let a profitable PAPER trade validate an economic causal claim.
- Never let presentation or Q&A exceed thesis/proof standing.
- Never mutate production. Never trade live. `PRODUCTION_BASELINE=119d345`.
- Never use `--no-verify`. Never weaken a test to make it green.
- Never mutate outside the verified session-owned repository root.

## A live cycle needs a frozen tree

Commit, then launch, then **do not touch `src/` until the cycle exits.**

A cycle is launched with `PYTHONPATH` pointing at the session worktree and
takes ten to twenty minutes. This module lazily imports inside functions, so
`steps.py` is loaded at process start and `report.py` near the end. Editing
`src/` in between produces one process running two revisions of the codebase.

`runtime_provenance` cannot catch it. It captures the SHA and the dirty flag
AT IMPORT — correct for the case it was built for, a branch moving under a
long run, and blind to the working tree changing under one. The artifact
reports a clean SHA and is not evidence for either revision.

This has happened once, on 2026-08-09: a cycle came back with
`economic_method: {}` because the projection existed and the step that fills
it did not. Twenty minutes, and the temptation was to debug the empty block.

Docs, `tests/` and `scripts/` are safe to edit during a cycle. `src/` is not.
The same rule covers break-proof runs, which mutate `src/` in place: never run
them while a cycle or a full suite is in flight.

## Per-node loop

    reconcile repo state
    -> update EXECUTION_LEDGER
    -> recompute dependencies
    -> rank READY nodes
    -> execute highest-value READY node
    -> validate (tests + a real run, not a fixture)
    -> record evidence
    -> commit + push
    -> recompute frontier
    -> continue

Do not ask the operator what is next while TASK_GRAPH contains READY work.

## Repair budget

On failure, attempt up to 3 *materially different* diagnoses. Do not repeat a
failed operation. If still blocked, set `NEEDS_REPAIR` with observed error,
attempted repairs, diagnostic evidence and likely prerequisite; restore unsafe
partial changes; recompute frontier; continue elsewhere.

External services get bounded retry/backoff, then `BLOCKED_EXTERNAL` with
measured evidence. An unreachable data source does not stop replay, scenarios,
Founder work or robustness.

## Stop conditions

Stop only when: no READY safe node remains; or all unresolved nodes are
terminal; or repository identity cannot be established; or credentials are
unavailable; or continuing would require fabricating scientific evidence; or a
safety/PAPER constraint forbids the operation.

Invalid reasons to stop: one test failed; one node is blocked; a sample is too
small for one experiment; assumptions failed for one method; a source is down;
the bandit is unevaluable; context is getting tight; one program finished; a
new bottleneck was discovered.

Context limit is not program completion. Before context becomes unsafe: finish
the current coherent slice, run tests, commit, push, update TASK_GRAPH,
EXECUTION_LEDGER and CURRENT_FRONTIER. A new session then resumes mechanically.

## Closure objective

    unresolved_executable_V4_requirements -> 0

Optimise downward: unknowns, unverified mechanisms, unattributed learning,
reward uncertainty, decision uncertainty. Do NOT optimise upward: lines of
code, classes, beliefs, reports.
