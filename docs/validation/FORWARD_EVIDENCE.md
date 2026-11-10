# Forward evidence — what is preregistered, and what is waiting

*Canonical. `reports/real_forward_expectations.jsonl` is the record;
`reports/v3_closure.json` is the derived ledger. This explains the contract.*

---

## The status, and why it will not move on demand

| | |
|---|---|
| real expectations open | **13** |
| real expectations resolved | **0** |
| calibration status | **PRE_CALIBRATION** |

`PRE_CALIBRATION` is not unfinished engineering. Not one real prediction has
reached its horizon, and an accuracy figure with an empty denominator is the
claim this whole programme exists to not make. `FounderEconomicContext`
raises if a calibration state other than `PRE_CALIBRATION` is asserted with
nothing resolved.

The earliest horizon in the ledger is in 2026-12; the latest is 2027-08. The
status changes when those dates arrive, and not before.

## The eight lifecycle facts, checked against the real file

1. an expectation opens with a cutoff, a horizon and a resolution rule
2. **its information cutoff precedes the date it was made**
3. it survives reload byte-identically
4. it cannot be edited retrospectively
5. it resolves only when the horizon has arrived
6. resolution APPENDS a new record and leaves the original
7. calibration consumes only resolved pairs
8. unresolved expectations never enter an accuracy figure

Fact 2 was added during closure. One real record carried an
`information_cutoff` and no `created_at`, because the relation generator
appended to the ledger directly rather than through `belief.Expectation`,
which requires the pair — so it could not answer the single question
preregistration exists to answer. The generator is repaired, the check now
requires it, and the existing record was **completed by appending a row whose
date comes from its own `code_sha`'s commit**, by a script that refuses rather
than guessing when the sha is unknown.

`assert_lifecycle` checks each expectation's CURRENT state rather than every
row: a resolution is a new line that does not repeat every field, so a
row-wise check would fail on every resolution the ledger ever takes.

## Rehearsal is a different file, and two barriers keep it out

REHEARSAL exists to prove the machinery can score itself on history. It is
not a track record and may never contribute to a customer-facing accuracy
figure.

- the reader opens only `real_forward_expectations.jsonl` — it does not know
  the rehearsal path
- `FounderEconomicContext.__post_init__` refuses any expectation whose
  `source` is REHEARSAL

The first is a convention about which file is opened; the second is a check
on what the row says. Both are exercised by break proofs.

## The FIRST_RELEASE wall

A contract declaring `FIRST_RELEASE` is resolved from the EARLIEST stored
vintage of the horizon period. Scoring it against a restatement published
afterwards would score the prediction on information it could not have had.
`forward_engine._readable` branches on the vintage policy, and the branch is
asserted structurally — release-blocking if it disappears.

## Relations, and why five of six are not failures

| state | n |
|---|---|
| CANDIDATE | 5 |
| SUPPORTED_PREDICTIVE | 1 |

5 of them are CANDIDATE because
**their driver did not move**, and 0
because the lag has not elapsed. Neither is a failure of the relation, and
the ledger records when each can next be judged so it is not re-reported as
non-firing every cycle.

A relation reaches `SUPPORTED_PREDICTIVE` only when the driver moved, the lag
elapsed, the target moved, the direction was correct and the magnitude was
plausible. One has.

## The relation → expectation seam

`scripts/open_relation_expectations.py` opens an expectation only when the
relation is SUPPORTED_PREDICTIVE, the driver moved beyond the declared
trigger, the lag has elapsed, and no open expectation already covers it. On
the last run it opened **zero** and named the reason for each of the six —
which is the correct outcome, and §20 forbids opening one to increase N.
