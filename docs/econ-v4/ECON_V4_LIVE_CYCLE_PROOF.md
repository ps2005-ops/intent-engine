# ECON_V4_LIVE_CYCLE_PROOF

## Deployment

| | |
|---|---|
| Runtime root | `/Users/prathamsharma/intent-engine-market` |
| HEAD before | `9b01ff1b10d3` |
| HEAD after | **`3b53037044c3`** |
| Remote | `origin/fix/econ-v4-calibration` = `3b53037044c3` (verified by `git ls-remote`) |

Pre-deploy backup: `~/econ-v4-backups/market-state-predeploy-20261011T070429.tar.gz`
(14 MB — `reports` + `data` + `status`).

The commit touches 31 files, **none** under `reports/`, `data/` or `status/`,
so the tracked-and-runtime-mutated `reports/funnel_history.json` carried
forward untouched. Verified by hash across the checkout:

```
ledger sha  6cf9630d6356f329e9a9 -> 6cf9630d6356f329e9a9   unchanged
funnel sha  08fac3d0907006555d84 -> 08fac3d0907006555d84   unchanged
ledger lines        21,358       -> 21,358                 unchanged
```

No cycle was active during the checkout. Nothing was force-pushed; `v5/market`
was not touched.

## Imports resolve from the intended tree

Run with the plist's exact environment
(`PYTHONPATH=…/intent-engine-market/src`, `TRADING_MODE=PAPER`,
`TZ=America/Toronto`, the symlinked venv's interpreter):

```
imported from            : …/intent-engine-market/src/intent_engine/market
learning_health CONTRACT  : market_learning_health.v2
has cap_mechanism_summary : True
new skip statuses         : SKIPPED_OUTSIDE_WINDOW / SKIPPED_LOCK_CONTENTION
SKIPPED_WITHOUT_RUNNING   : (DUPLICATE, OUTSIDE_WINDOW, LOCK_CONTENTION, STALE_DATA)
```

This matters because the runtime `.venv` is a symlink to the *founder* venv,
whose editable install points at a tree with no `market` package. Production
works only because the plist prepends `PYTHONPATH`, so the check above is the
one that proves the deployed code is the code that runs.

## A real cycle on the deployed code

Run against an isolated copy of production state, so the `2026-10-11:night`
run identity stayed free for the 20:30 scheduler — a real cycle on real data
without consuming the production slot.

```
2026-10-11:night:America/Toronto  COMPLETED
  weekend — evidence and research cycle only
  ok research · ok source_acquisition · ok reconcile · ok paper_resolve
  ok opportunity · ok resolve_outcomes · ok funnel · ok positions
  ok assets · ok learning · ok knowledge · ok learning_health
  ok replay · ok health · ok report
EXIT=0
```

15 of 15 steps ok. Duration ~22 min.

### What the deployed code persisted

```
contract                 : market_learning_health.v2
incoherent_pairs         : 2
capped_by_causal_ceiling : ['demand_strengthening']
by_maturity              : {CONTESTED: 1, EMERGING: 2, FAILING: 1,
                            UNFALSIFIABLE_BY_OBSERVATION: 12}

demand_strengthening   CONTESTED   19C/1X   <== CAPPED from ESTABLISHED
demand_weakening       FAILING      1C/6X
market_share_seeking   EMERGING     1C/1X
pricing_power          EMERGING     2C/1X

hit_rate                 : 0.71875
expectation_calibration  : absent (the mislabelled key is gone)
brier / climatology      : 0.2138 / 0.2021   skill -0.0576
```

`ESTABLISHED` appears nowhere in the published counts. Both repairs are now in
a durable artifact written by a real cycle, not only in a read-only probe.

## Restart / reload proof

Fresh process, nothing in memory, state re-derived from the persisted ledger:

```
snapshots on record      : 63
last snapshot as_of      : 2026-10-11
last snapshot contract   : market_learning_health.v2
re-derived beliefs       : 132
persisted beliefs        : 132          match: True
cap survives reload      : ('demand_strengthening',)
ESTABLISHED published    : 0
hit_rate re-derived      : 0.71875
```

## Scheduler

Unchanged — no duplicate agent created. Both plists still point at
`/Users/prathamsharma/intent-engine-market`, which is the worktree just
advanced, so the next scheduled run executes the deployed code.

| | |
|---|---|
| Next cycle | **night, today 20:30 America/Toronto** |
| Then | day, tomorrow 06:30 America/Toronto |

## Production cycle observed earlier today

The scheduled 06:30 `day` cycle ran on the *old* SHA (it fired before
deployment) and completed normally in ~29 min:

| | 06:12 | after |
|---|---:|---:|
| ledger records | 21,065 | 21,358 (+293) |
| beliefs | 131 | 132 |
| beliefs never tested | 99 | **100** |
| evidence items | 924 | 930 |
| expectations resolved | 32 | **32** |

One new belief, and it is untested — on `regulatory_pressure`, a family
classified `NOT_A_CAUSAL_MECHANISM`. **Zero reconciliations.** The status line
still read `LEARNING_ACCELERATING`.
