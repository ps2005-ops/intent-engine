# ECON_REPOSITORY_RUNTIME_TRUTH

Generated from canonical state. Every figure below is read, not asserted.

## Roots and worktrees

```
/Users/prathamsharma/intent-engine         840003f7 [growth-os]
/Users/prathamsharma/ie-asi-v2             b49a6565 [v6/asi-v2]
/Users/prathamsharma/ie-deploy             cfd4c3ba [fix/guest-demo-resilience]
/Users/prathamsharma/ie-econ-v4-dev        9b01ff1b [fix/econ-v4-calibration]
/Users/prathamsharma/intent-engine-econ    db6946fa [v6/unified]
/Users/prathamsharma/intent-engine-market  9b01ff1b (detached HEAD)
```

Runtime root: `/Users/prathamsharma/intent-engine-market`
Runtime HEAD: `9b01ff1b10d3554a343c4cba63923a46373a8215`
Dev root:     `/Users/prathamsharma/ie-econ-v4-dev`
Dev branch:   `fix/econ-v4-calibration`

The runtime worktree is a **detached HEAD pinned by SHA**, which is why a
branch cannot be checked out there and why code work happens in the dev
worktree above.

## Interpreter and import path

The runtime `.venv` is a **symlink** to `/Users/prathamsharma/intent-engine/.venv`,
whose editable install points at the *founder* tree, which contains no
`market` package. Production therefore works only because the plist prepends
`PYTHONPATH`. Any invocation that drops it either crashes or silently tests
the wrong tree.

```
.venv -> /Users/prathamsharma/intent-engine/.venv
python  Python 3.9.6
PYTHONPATH=/Users/prathamsharma/intent-engine-market/src   (set by the plist)
```

## Scheduler

Three launchd agents, not cron and not Render:

| label | schedule | runs | last exit |
|---|---|---:|---:|
| `com.intentengine.market.day` | 06:30 America/Toronto | 63 | 0 |
| `com.intentengine.market.night` | 20:30 America/Toronto | 60 | 0 |
| `com.intentengine.market.health` | RunAtLoad + periodic | 730 | 0 |

`TRADING_MODE=PAPER` is set in every plist.

## Cycles actually recorded

113 cycle records in the ledger: {'night': 62, 'day': 51}
Outcome classes: {'NEW_KNOWLEDGE': 51, 'BELIEF_MOVEMENT': 62}

## Cycle outcomes as the scheduler saw them

Tallied from the launchd stdout logs:

| outcome | count |
|---|---:|
| `SKIPPED_NO_NEW_MARKET_SESSION` | 78 |
| `COMPLETED` | 44 |
| `SKIPPED_DUPLICATE` | 19 |

**Finding — silent skipping.** `SKIPPED_DUPLICATE` means a cycle exited
because *another cycle held the lock*; it still exits 0, so launchd records
success and the health job reports 100% step reliability. Day cycles are
missing from the ledger for several dates in the audit window for this reason,
while every monitoring surface reported healthy.

A single launchd invocation also **replays a backlog of dates**, so one
process can emit many outcomes — which is how a lock collision arises between
a long-running invocation and the next scheduled one.

## Ledger integrity

`learning_ledger.jsonl`: 21065 records, all valid JSON.
Record types: {'knowledge_effect': 4283, 'method_assumption_check': 4236, 'evidence_seen': 3287, 'method_performance': 3177, 'macro_observation': 2714, 'thesis_snapshot': 951, 'evidence': 924, 'source_health': 702, 'belief': 131, 'expectation': 131, 'research_decision': 119, 'research_outcome': 119, 'cycle': 113, 'relationship': 63, 'reconciliation': 32, 'belief_update': 32, 'causal_estimate': 25, 'thesis_revision': 24, 'relationship_support': 2}

## Cross-system transport

`reports/market/dossier_consumption.jsonl` present on this root: **NO**

The founder side's producer (`external_intel/consumption_receipt.py`) writes to
its own runtime root; this consumer reads the Mac root. No receipt has ever
landed where learning health is computed, which is why founder utility reports
`UNMEASURABLE`.
