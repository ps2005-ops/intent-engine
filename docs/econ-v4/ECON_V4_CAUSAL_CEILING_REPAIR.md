# ECON_V4_CAUSAL_CEILING_REPAIR

## The defect

`calibration_consistency` has been able to compute, since it was written, the
ceiling a mechanism's causal standing places on its published maturity. The
tables are complete and correct (`_CAUSAL_CAP`, `_MECHANISM_CAP`,
`_MATURITY_RANK`, `_MECHANISM_RANK`), `check()` detects every violation, and
nine deterministic tests prove the logic.

**Nothing applied it.** No module under `src/` imported
`calibration_consistency`; the only references in the repository were in
`scripts/break_proofs_wave5.py`, which reads the file as text. So
`learning_health.assess` published:

```python
health.mechanisms = MC.summarise(MC.calibrate(rows))
```

with no cap, and `demand_strengthening` — 19 confirmations, 1 contradiction,
reliability 0.95 — reached the operator surface as **ESTABLISHED** while its
own causal family stood at **CONTESTED**.

This is the repository's recurring failure mode: a subsystem specified,
tested, and never routed. Detection without application.

## The distinction that was collapsed

| question | measured by | answer for `demand_strengthening` |
|---|---|---|
| How often was the rule right? | hit rate | 19/20 = 0.95 |
| Is the effect identified? | causal grade | **CONTESTED** |
| May it be read as a mechanism? | `_CAUSAL_CAP[CONTESTED]` | **no — cap at CONTESTED** |

A high confirmation rate measures prediction. It is not evidence of
identification, and publishing it as maturity asserts the second from the
first.

## The repair

`calibration_consistency.cap_mechanism_summary(summary, incoherences)`:

- rewrites each breaching mechanism's `maturity` to `Incoherence.permitted`;
- keeps the overridden value as `maturity_uncapped`, plus `capped_by`,
  `capped_because` and `causal_standing` — a cap that hides what it overrode
  is just a different wrong number;
- recomputes `by_maturity` so the published table cannot contradict its own
  rows;
- reports every incoherence, including belief-level ones that do **not** cap a
  mechanism;
- does not mutate its input.

`learning_health.assess` now publishes through it. There is deliberately **no
`try/except` around `check()`**: swallowing a failure there would silently
restore the uncapped publication this exists to prevent — the cap would look
applied and not be.

The ledger, the reconciliations and the hit rate are untouched. No historical
observation was rewritten to make the display coherent.

## Live proof — read-only, production ledger, 2026-10-11

Before:

```
demand_strengthening   ESTABLISHED   conf=19 contra=1 rel=0.95
by_maturity: {UNFALSIFIABLE_BY_OBSERVATION: 12, ESTABLISHED: 1, FAILING: 1, EMERGING: 2}
```

After:

```
incoherent_pairs        : 2
capped_by_causal_ceiling: ('demand_strengthening',)
by_maturity             : {UNFALSIFIABLE_BY_OBSERVATION: 12, CONTESTED: 1, FAILING: 1, EMERGING: 2}

demand_strengthening   CONTESTED   conf=19 contra=1 rel=0.95   <== CAPPED from ESTABLISHED (causal=CONTESTED)
demand_weakening       FAILING     conf=1  contra=6 rel=0.143
market_share_seeking   EMERGING    conf=1  contra=1 rel=UNMEASURABLE
pricing_power          EMERGING    conf=2  contra=1 rel=UNMEASURABLE
```

`ESTABLISHED` no longer appears anywhere in the published counts. The hit rate
is unchanged and still visible, which is the point: both facts are true and
both are reported.

## The second incoherence

```
BELIEF_ABOVE_ITS_MECHANISM_CEILING
  family  : demand_weakening
  subject : johnson_johnson
  why     : the mechanism is FAILING across every subject, so one belief's
            confirmation count cannot carry it past WEAKENING; counting
            confirmations of a single instance does not promote the rule
```

Reported, and deliberately does **not** cap a mechanism — only
`MECHANISM_ABOVE_ITS_CAUSAL_CEILING` does. A belief-level breach is a
belief-level finding. Pinned by
`test_a_belief_level_incoherence_does_not_cap_a_mechanism`.

## Regression tests

`tests/test_causal_ceiling_applied.py`, 14 tests, including the one §3.2 asks
for by name:

- `test_a_high_hit_rate_cannot_publish_above_a_contested_causal_ceiling` —
  19/20 at reliability 0.95 publishes CONTESTED, not ESTABLISHED.
- `test_the_overridden_grade_is_preserved_not_erased`
- `test_the_published_counts_agree_with_the_published_rows`
- `test_no_incoherence_leaves_every_grade_untouched` — the cap cannot fire
  spuriously.
- `test_only_a_contested_causal_family_lowers_the_ceiling` (parametrised over
  all five causal standings) — an *unmeasured* causal family is not evidence
  against the rule and must not lower anything.
- `test_learning_health_actually_applies_the_cap` — asserts the publication
  path goes through the cap, because the original defect was a correct and
  unused function.
- `test_some_module_under_src_imports_calibration_consistency` — asserts the
  module has a consumer at all. A ceiling nothing applies is not a ceiling.

The last two exist because "the code is correct" was already true before this
repair and was not sufficient.
