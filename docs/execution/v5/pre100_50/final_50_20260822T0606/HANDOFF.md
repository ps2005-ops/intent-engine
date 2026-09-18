# Stopped — closure run reassigned

This batch was stopped on the owning session's request. No live analyses are
running from here and the batch lock is released.

## What is on disk, and its limits

Five captures on **02f4644**, which is an ANCESTOR of the deployed b0ec8cb.
They cannot carry to the new SHA and should be re-run:

| company | seconds | core_mean | note |
|---|---|---|---|
| Alphabet Inc. | 518 | 9.64 | |
| Microsoft Corporation | 516 | 9.27 | |
| Amazon.com, Inc. | 661 | 9.27 | |
| Meta Platforms, Inc. | 1383 | 8.36 | core_min 0 on `economic_reasoning` |
| Salesforce, Inc. | 440 | 2.6 | quarantined as `_restart_lost_salesforce_inc` |

Salesforce was quarantined because the instance reported 62s uptime right
after it finished. I read that as memory-pressure restart; given the
corrupt-log finding it is more likely the ledger tearing under it. Either
way the row is not intelligence quality and should be re-measured, which
matches the owning session's plan.

## Harness work committed here (local only, deliberately unpushed)

Pushing redeploys and kills in-flight runs, so `581a0b2` was never pushed.
Cherry-pick if useful:

* **restart detection** — `boot_id()` sampled before and after each company;
  a change classifies `RUN_RESTART_LOST`, quarantines the capture, requeues
  the company and scores nothing. Two tests.
* 25 harness-contract tests total, including: a 429 defers and requeues
  rather than counting as a strike; an exclusive `BatchLock` (O_EXCL on a
  PID file, stale locks reclaimed); slug parity with the journey; the
  journey must fetch every surface either scorer reads, derived from
  `DIMENSIONS` and `FIELDS` so it cannot drift; failed captures persist the
  non-2xx body.
* scorer repairs with controls: the absence list no longer caps a dimension
  on a provenance qualifier ("read from the business model, not retrieved"
  had capped ten good Microsoft answers at 3); identifiers are stripped in
  specificity normalisation, with a control asserting the Adobe/Salesforce
  byte-identical pair is still detected.

## Correction worth carrying forward

I reported the /analyze 500 as confirmed accumulated ephemeral state,
because a fresh container recovered. That inference was unsound: a redeploy
wipes the ephemeral log, so recovery is consistent with several causes. The
owning session read the actual stderr — `IngestionCorruptLogError:
data/company_ingestion.jsonl line 145 is malformed` — which is the real
mechanism and explains why nine surfaces died together while `/report`,
a different reader, stayed up.
