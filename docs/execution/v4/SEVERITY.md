# Severity classification — the rule that lets the graph converge

## What this fixes

The maturity audit works. That is the problem it created.

Every deeper verification found another missing read path, another
uninstrumented capability, another seam nobody had measured — and each one
became a new `READY` node. Two runs in a row closed three nodes and opened
three. `READY` went 7 → 8 while the software got materially better. On that
rule V4 cannot finish, not because the work is endless but because the
*definition* of the frontier grows as fast as the frontier is consumed.

So discoveries are now classified, and only two classes may extend the
release frontier.

## The four classes

**RELEASE_BLOCKER** — V4 cannot be called complete with this defect present.
It produces a wrong answer, a fabricated record, or a claim the evidence does
not support. Opens a `READY` node.

**MATERIAL_DEFECT** — a capability that is claimed and does not work: an
implemented thing with no production caller, a write path with no read path, a
guard that cannot fire, a count nobody can observe. Opens a `READY` node.

**HARDENING** — the behaviour is correct and could be made more robust,
faster, or better covered. Recorded in `BACKLOG.yaml`. Does **not** open a
`READY` node unless a current release invariant names it.

**FUTURE_IMPROVEMENT** — new capability, however good the idea. Goes to V5.
Does not open a node.

## The test that separates MATERIAL_DEFECT from HARDENING

> Does the system currently make a claim that this defect falsifies?

If a report, a matrix cell, a ledger row or a node's `completion_evidence`
asserts something that is not true because of this, it is MATERIAL. If the
claim is true and merely narrow, it is HARDENING.

`effects_bearing_on` comparing `"CAPITAL_INTENSITY"` against
`"acme:CAPITAL_INTENSITY"` was MATERIAL: two live reports said the
attribution rule ran and attributed nothing, and that read as a strict rule
nothing tripped. It was a rule that could not fire.

Adding a second exposure-id format for a producer that does not exist yet
would be HARDENING.

## Where each goes

| class              | TASK_GRAPH | BACKLOG.yaml | EXECUTION_LEDGER |
|--------------------|------------|--------------|------------------|
| RELEASE_BLOCKER    | READY node | –            | classified entry |
| MATERIAL_DEFECT    | READY node | –            | classified entry |
| HARDENING          | –          | yes          | classified entry |
| FUTURE_IMPROVEMENT | –          | V5 section   | classified entry |

Every discovery is recorded either way. The classification decides whether it
blocks a release, not whether it is remembered.

## The audit is done once

`COMPLETE_NODE_MATURITY_AUDIT` is a one-time systematic pass over COMPLETE
nodes whose acceptance implies runtime use, recorded in `MATURITY_AUDIT.md`.
After it is marked DONE, the global audit is not repeated every session.
Later defects surface the ordinary way — through tests, through live cycles,
and through the node currently being worked.

This is not a decision to stop looking. It is a decision to stop *re-deriving
the same survey* and to let the frontier be consumed faster than it is
extended.
