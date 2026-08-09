# CURRENT FRONTIER

Resume pointer. A new session needs only this file plus AGENT_PROTOCOL.md.

    python3 docs/execution/v4/metrics.py --write   # remeasure the data gates
    python3 docs/execution/v4/frontier.py          # what is runnable
    python3 docs/execution/v4/frontier.py --check  # fails if drift reappeared

Do not trust this file over the script. If they disagree, the script is right.

## Repository, before anything else

The market checkout is a **linked worktree of `/Users/prathamsharma/intent-engine`**;
`git rev-parse --git-common-dir` from the market root returns the Founder
repo's `.git`. Consequences a resuming session will otherwise rediscover:

- The pre-commit hook lives in the Founder repo's shared hooks dir and runs
  the offline suite. It needs `GUARD_PYTHON=/Users/prathamsharma/intent-engine-market/.venv/bin/python`
  in a worktree. `--no-verify` is never the fix, and neither is
  `-c core.hooksPath=…`, which is the same thing wearing a different hat.
- `origin/v4b/market` is the source of truth. The local `refs/heads/v4b/market`
  may be pinned by another session's worktree registration; `git update-ref`
  moves it without touching that directory.
- The venv at `intent-engine-market/.venv` resolves `intent_engine` to the
  FOUNDER tree unless `PYTHONPATH` names the market source root. Every command
  below sets it.

Run tests from the repo root — several read repo-relative paths and fail from
anywhere else, which looks like a broken test and is a broken invocation:

    env -C <worktree> PYTHONPATH=src <venv>/bin/python -m pytest tests -q

## The convergence rule (new, and the point of this run)

`SEVERITY.md`. Only **RELEASE_BLOCKER** and **MATERIAL_DEFECT** may open a
READY node. **HARDENING** and **FUTURE_IMPROVEMENT** go to `BACKLOG.yaml` and
do not extend the release frontier.

This exists because the maturity audit was working too well to finish: two
runs closed six nodes between them and READY went 7 → 8. Every discovery is
still recorded; the classification decides whether it blocks a release.

`COMPLETE_NODE_MATURITY_AUDIT = DONE` (see `MATURITY_AUDIT.md`). The global
survey is not repeated per session. The ladder is enforced per node through
`maturity_required` and through live cycles — which is how G-THE-004 was
found, not by an audit.

## What G-THE-004 turned out to be

The recorded diagnosis was wrong, and instructively so. It said the prior
snapshot dict kept only the last thesis per identity. Reading the ledger:
**all seven persisted snapshots had distinct identities.**

The collision was on the CURRENT side and started two layers up. An
`EconomicState` is keyed `(area, state_kind)`; `from_transmission` kept only
the kind. `CA:MARKET_RATE` and `US:MARKET_RATE` are two states, and for one
company they produced two theses with byte-identical claims, one `thesis_id`,
and one snapshot — the store is idempotent on `(thesis_id, as_of)` and
returned `False` for the other four of eleven. **Four theses were never
persisted, every night, and nothing counted the refusal.**

`compared: 11 > loaded: 7` was the symptom. Repairing `reconcile` alone would
have made the arithmetic legal and left four theses unpersisted.

Two more defects surfaced from the same seam, both live for two cycles:

1. **The attribution wall could not fire.** Exposure effects carry
   `target_id = "company:DIMENSION"`; the basis was built from the bare
   dimension. `unattributed 0` read as a strict rule nothing tripped. Test
   fixtures had been passing already-qualified exposures, so the only shape
   ever exercised was one production does not emit.
2. **The revision chain was rebuilt empty every night**, so every row ever
   written had an empty parent. The write path was verified; nothing read it
   back. `prior_revisions_loaded` now discriminates — `written: 0` reads the
   same whether the chain was loaded and nothing moved or never loaded at all.

## Findings a resuming session must not re-derive

1. **VOIPolicy is a constant, not an estimate.** Identical to
   `FixedPolicy(regulatory_filing)` on all six figures. See B-VOI-001.

2. **Persistence is the bar for macro levels, and it now holds by rule.**
   Over the 15 live series: 36 NO_INCREMENTAL_VALUE, 6 BOUNDED, 3 REFUSED.
   Every method that beat persistence came back BOUNDED or REFUSED — **not
   one is USEFUL.** The five short-series wins (23–24 points, ~16 held-out
   predictions) are bounded by a 30-prediction floor; the one long-series win
   (AR1 on `GLOBAL:CURRENCY`, 519 points, skill 0.0043) is REFUSED because the
   fitted coefficient is 0.9854 and a unit root makes that mean reversion a
   finite-sample artefact. C-MET-001's "suggestive, not promoted" is now
   enforced by the standing rule rather than restated in prose.

3. **The market venv is the Founder venv.** See above.

4. **An assumption check that fails on everything is as useless as one that
   passes on everything, and more convincing.** Two first implementations
   were wrong and only visible against real data: stationarity screened on
   the levels' autocorrelation rather than on the coefficient the method
   actually fits, and residual autocorrelation computed from walk-forward
   forecast errors — which an expanding-window fit makes negatively
   autocorrelated by construction, so every series on earth "failed".

5. **A store accessor with no production caller is not a missing read path.**
   `knowledge_step` loads every ledger line as raw dicts and each module
   filters by `record`. Auditing the typed accessors reported twelve
   capabilities with no reader and would have opened a dozen nodes. Only
   `knowledge_effect` genuinely has none, and attribution does not depend on
   it (`BKL-EFFECT-READBACK`).

6. **A caller is not a call.** A-RD-009 was COMPLETE and had never executed:
   `knowledge_step` called `RD.credit_revisions(...)` with `RD` bound as a
   local in four OTHER functions. `NameError` every cycle, swallowed by
   `except Exception`, invisible because nothing projected the block. It was
   found by adding the projection — the instrumentation falsified the node it
   was instrumenting. A wiring test now asserts no knowledge block reports an
   error on ordinary data.

## What is still architectural rather than empirical

**No empty-handed research row has ever occurred in production.** All 12
prospective outcomes are SUCCESS. The cause is measured and it is SELECTION,
not logging: the sweep offers three families, cadence gates one, and the two
that run are the two that reliably return documents. Refusals are already
recorded as ineligible candidates with reasons.

The classifier was unit-tested across all six statuses, which proves the
classifier. `tests/test_market_unsuccessful_research_outcomes.py` now drives
the real acquisition step with adapters that raise, return nothing and return
only refusals, and asserts the persisted status. **Production's `NO_RESULT`
count is still zero and must not be manufactured** — what changed is that the
zero can be told apart from an incapacity. Rate is ~2 decisions per cycle;
the 100 gate is tens of cycles out.

**No thesis has moved.** 18 revisions, all CREATED. `classify()` has executed
on real data and found nothing to classify, so STRENGTHENED / WEAKENED /
CONTESTED have never been produced live, and the delayed reward has never
paid anyone — correctly, since a first statement is not a consequence of any
action. Do not synthesize a transition.

## Next action

Run `frontier.py`. Do not assume the order in this file still holds.

As of `5ffca7e`: 43 nodes, COMPLETE 23, READY 6, WAITING_DEPENDENCY 11,
BLOCKED_DATA 3. Runtime pinned to `5ffca7e`, imports verified, PAPER
enforced, production `119d345` untouched.
