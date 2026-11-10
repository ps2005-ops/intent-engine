# COMPLETE-node maturity audit — the one systematic pass

    COMPLETE_NODE_MATURITY_AUDIT = DONE   (2026-08-09)

Scope: the 20 V4 nodes marked COMPLETE at `4561ee9`, and only those. No
speculative future capability was inspected and no new requirement invented.
The question asked of each was the one that produced G-THE-002, A-RD-009 and
G-THE-004:

> Does anything in production call this, does it persist what it computes,
> does anything read that back, and has the result been checked for meaning
> rather than for presence?

## The method, and the way it was wrong first

The first pass grepped for production callers of the store's typed reader
methods (`store.knowledge_effects()`, `store.relationships()`, …) and reported
twelve capabilities with "NO PRODUCTION READER". That number was wrong, and
wrong in the direction that would have opened a dozen nodes.

Production does not read the ledger through the typed accessors. `knowledge_step`
loads every line of `learning_ledger.jsonl` into a list of raw dicts once, and
each module filters it by `record` kind. So a typed accessor with no caller is
usually a convenience used by tests, not a missing read path.

Measuring the accessors was measuring the wrong thing. The audit was redone
against the raw-row filters, which is where the read path actually lives.

## What it found

| capability | production caller | persists | read back | verdict |
|---|---|---|---|---|
| research decisions / outcomes / delayed | yes | yes | yes | sound |
| thesis revisions | yes | yes | yes — added in G-THE-004 | was a gap, now closed |
| thesis snapshots | yes | yes | yes | sound |
| macro observations | yes | yes | yes | sound |
| reconciliations | yes | yes | yes (4 raw-row filters) | sound |
| economic_method | yes — added in C-MET-004 | yes | yes | was a gap, now closed |
| vintage | none | n/a | n/a | correctly waiting on D-REP-002 |
| knowledge effects | yes | yes | **no** | see below |

One finding, and it is HARDENING rather than a defect:

**`knowledge_effect` rows are written and nothing reads them back.** Attribution
does not break, because `knowledge_step` recomputes the effects over the FULL
evidence history every cycle — `CX.profile` is handed every evidence row ever
stored, not tonight's. So the effect an old piece of evidence produced is
present in memory whether or not the persisted copy is ever opened.

It is recorded rather than fixed because nothing currently claims otherwise,
and because the condition that would make it material is specific and worth
naming: `BKL-EFFECT-READBACK` in `BACKLOG.yaml`.

Capabilities outside the V4 COMPLETE set — relationships, falsifiers,
response watches, strategic objectives and interactions, cross-actor
expectations, counterfactual adjudications — were **not** audited. They belong
to V3 and inspecting them here is the scope expansion §36 forbids.

## Why this is not repeated every session

Three runs in a row, the global audit found something and each finding became
a READY node. That is the audit working, and it is also why `READY` went 7 → 8
across two runs that closed six nodes between them. An audit that runs every
session extends the frontier at roughly the rate the frontier is consumed.

The ladder that produced these findings —

    IMPLEMENTED -> INSTRUMENTED -> READ_BACK -> SEMANTICALLY_CORRECT

— is not being abandoned. It is now enforced per node, at the moment a node is
worked, through `maturity_required` and through live cycles. What stops is the
repeated global survey.

Later defects will surface the way G-THE-004 did: from running the thing. That
one was not found by an audit. It was found because G-THE-003 forced a second
cycle instead of accepting "revisions are live", and the second cycle printed
two numbers that could not both be true.
