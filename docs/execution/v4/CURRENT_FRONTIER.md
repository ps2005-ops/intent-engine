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
  is usually pinned by another session's worktree; `git update-ref` moves it
  without touching that directory.
- The venv at `intent-engine-market/.venv` resolves `intent_engine` to the
  FOUNDER tree unless `PYTHONPATH` names the market source root.

**THE RUNTIME IS THE CANONICAL CHECKOUT ITSELF.** launchd runs
`/Users/prathamsharma/intent-engine-market/.venv/bin/python -m intent_engine.market`
with `PYTHONPATH=<that root>/src`. So "repin the runtime" means `git checkout
<sha>` in `/Users/prathamsharma/intent-engine-market` — and it means a live
cycle is reading THAT tree, not your worktree. Editing your own worktree
during a cycle is safe; editing the canonical checkout is the mixed-revision
trap `runtime_provenance` cannot catch.

Run tests from the repo root — several read repo-relative paths:

    env -C <worktree> PYTHONPATH=src <venv>/bin/python -m pytest tests -q

## The convergence rule

`SEVERITY.md`. Only **RELEASE_BLOCKER** and **MATERIAL_DEFECT** may open a
READY node. **HARDENING** and **FUTURE_IMPROVEMENT** go to `BACKLOG.yaml`.

**The governing-plan exception is now SPENT.** Five systemic pillars were
adopted after this graph was derived and were reconciled into it once, on
2026-08-09, as PROGRAM L. They are not to be rescoped again session by
session.

## The permanent rule this program keeps re-learning

**ABSENCE MUST NEVER IMPERSONATE A NEGATIVE FACT.** The same defect has now
been found five times in five different layers:

    a degraded source                 read as "no economic activity"
    missing thesis history            read as "the thesis never changed"
    no prior DecisionImpact baseline  read as "the intelligence changed it"
    an empty strategic section        read as "no market intelligence exists"
    an empty before-state             read as "every dossier changed a decision"

`NONE`, `NO_CHANGE`, `UNAVAILABLE`, `NOT_OBSERVED`, `BLOCKED_DATA` and
`FAILED` are six different states. Before explaining anything to a founder,
the system has to know which one it is in. When adding any new reader, ask
what its empty case is and whether it can tell that from a measured zero.

## H-CEO-002 is COMPLETE — thesis history crosses the bridge

TWO missing production callers, not one. `economic_theses` was ALREADY an
allowlisted export field with a projector, and `strategic_publish` never
passed it. `thesis_revisions` had no field at all. The ledger has carried 18
revision rows with effects, evidence and both standings the whole time.

`thesis_history.status` is STATED, never inferred from the list's length —
"no revisions crossed" and "no revision exists" are the same empty list. A
producer sending no status is UNAVAILABLE, not NO_MOVEMENT.

Verified on the live ledger: america_movil 8/8, honda 2/2, linde 8/8, every
one `HISTORY_AVAILABLE_NO_MOVEMENT`. That is the honest reading — all 18 live
transitions are CREATED. **The transport is proven without a single thesis
having moved**, which is the point: it will be right the first time one does.

## H-CEO-001 is STILL HALF DONE — and no longer blocked

**Done and break-proven:** decision-impact measurement. The instrument
existed all along, was deterministic, was wired, and had never written a
record. Exercising it on all 59 live dossiers showed why it could not have
helped: 25 available, 16 DECISION_CHANGING, 9 MEANINGFUL, **zero NONE** —
because the BEFORE was `build_context(strategic=None)`, empty on all five
fields. It measured whether a dossier was attached. The BEFORE is now the
prior revision, `FIRST_OBSERVATION` is a third outcome entering neither side
of the rate, and 10 mutation proofs hold — including restoring the empty
BEFORE and watching NONE disappear.

**FOUNDER_VALUE is still UNMEASURABLE and that is correct.** All 25 live
records are baselines. It clears on the first dossier revision that differs.
Do not manufacture one.

**Not done: the CEO Q&A half.** The transport that blocked it is now closed,
and `decision_impact.what_changed_your_mind` answers that one question from
the record with three distinct states. The remaining fourteen questions, the
answer planner and challenge mode are unbuilt.

Build the planner on the EXISTING conversation/provenance layer
(`founder_intelligence/conversation.py`), which already scopes claims to one
run and validates them. Do not start a second reasoning engine.

## What the session before that changed (E-DEM-001)

**The demand problem was never a reasoning problem.** The node reads
"targeted demand-variable extraction" and the obvious move was to add
detectors. Measuring first said otherwise: six of ten demand states stood at
ZERO companies and the words were absent from the corpus text entirely — 0
raw hits across 348 evidence rows. Detectors would have extracted nothing and
looked built.

`company_ingestion.parsing` buffered text only inside a block whitelist with
no `<div>`, and SEC filings write prose in `<div>`/`<font>`. On a real
Caterpillar exhibit it kept **13,462 of 64,547 characters**: every numeric
`<td>` survived and every sentence of narrative did not. Live after the
repair: candidates 1281 → 1815, evidence 105 → 134, navigation 9 → 11.

Then the reader. The existing phrase list, used as a detector, scores
**precision 0.50** on a labelled corpus — and its errors are four different
questions, not one:

    "We placed orders for new equipment"      the company BUYING
    "Komatsu reported strong bookings"        a rival's demand
    "We expect bookings to improve"           an expectation
    "reduced its ticket backlog by 40%"       another domain

`demand_extraction` asks them separately: **1.00 / 1.00**, refusal reasons
agreeing with the labels. Live: DEMAND_SIGNAL 21 rows, coverage 18 → 23
cells, and the dated report now carries a real demand contradiction —
`infosys: REVENUE->GUIDANCE`.

**Coverage FELL first, 23 → 18, and that was the result.** The old count
included a vendor's case study about what a CUSTOMER achieved and product
copy listing "revenue reporting" as a feature. Adjudicate refusals before
believing a coverage number.

**BOOKINGS, BACKLOG, CANCELLATIONS, SHIPMENTS and END_DEMAND are still zero,
and that is the CORPUS.** The same reader extracts BACKLOG / UP / OBSERVED
from a real Caterpillar filing end to end. These 27 companies' fetched
sources do not state those figures. Do not "fix" it with looser patterns.

## What the session before that changed

**I-ACC-001 is COMPLETE and live at `80f3aa5`.** Seven learning channels
derived from the effect log, never averaged. Three defects were found in its
own seam and all three were live:

1. **The block never reached the record.** `knowledge_step` computed
   `learning_acceleration` every cycle since the module was written;
   `report._knowledge_summary` is a WHITELIST and did not name the key, so the
   whole result was discarded on the way to the dated artifact. Nothing
   raised, nothing logged. Meanwhile the report's section *titled* LEARNING
   ACCELERATION renders `throughput.py` — securities evaluated, signal fires
   — so a reader asking whether the engine learns saw trading volume. Same
   shape as *a caller is not a call*, one layer out.
2. **An absent link reported as a measured zero.** The research channel first
   graded 0 of 14 outcomes productive; all 14 carry an EMPTY
   `knowledge_effect_ids`. It now returns UNMEASURABLE and names the field.
3. **Founder value was publication volume.** The call site passed
   `len(strategic_export.published)`. The channel reads decision-impact
   records and reports UNMEASURABLE, which is the true state.

**L-SRC-001 is built, proven and committed at `8f14906`.** Source health is a
persisted state per family per cycle, with streak and `last_success`.

## The live reading, and what it means

    ECONOMIC      29/402  (7.2%)   DEGRADING  MATURE
    SYSTEM        20/41            INSUFFICIENT_HISTORY (one day)
    CALIBRATION    3/11            STABLE     EARLY
    FOUNDER          —             UNMEASURABLE
    RETENTION    402/402           STABLE     MATURE
    RESEARCH         —             UNMEASURABLE
    UNSUPERVISED   1/3             EARLY_WARNING

`HIGH_ACTIVITY_LOW_LEARNING` fires: 347 evidence rows, 373 attributions that
moved nothing, **0 thesis transitions**. That is not a defect in the metric.
It is the engine, measured.

Bottleneck computes to **FOUNDER_VALUE (UNMEASURABLE)** — the ranking puts an
unmeasured channel above a badly measured one, because a capability nothing
measures cannot be improved on purpose. Do not hardcode a different one.

## Findings a resuming session must not re-derive

1. **`created_at` on effects is NOT a write time.** 347 of 402 are written by
   the exposure fold with `created_at` = the EVIDENCE'S observation date, on
   purpose: `effect_id` is keyed on it, and a stable value is what stops the
   nightly re-derivation appending 347 rows a night. Windowing learning on it
   yields a history running back to February in a log whose write path landed
   on 2026-08-09. **Windows key on ledger APPEND ORDER, delimited by `cycle`
   records.** Break proof 13 (v4h) mutates the key and the guard holds. The
   field's mislabelling is real, and its migration would change every
   `effect_id` on a live append-only ledger, so it is in BACKLOG, not here.

2. **VOIPolicy is a constant, not an estimate.** Identical to
   `FixedPolicy(regulatory_filing)` on all six figures. See B-VOI-001.

3. **Persistence is the bar for macro levels, and it holds by rule.** Over 15
   live series: 36 NO_INCREMENTAL_VALUE, 6 BOUNDED, 3 REFUSED. **Not one is
   USEFUL.**

4. **The market venv is the Founder venv.** See above.

5. **A store accessor with no production caller is not a missing read path.**
   `knowledge_step` loads the ledger as raw dicts and each module filters by
   `record`. Only `knowledge_effect` genuinely has none.

6. **A caller is not a call.** A-RD-009 was COMPLETE and had never executed.

7. **The market pipeline has no LLM call site.** Measured, not assumed. The
   prompt-injection boundary is the seam into Founder reasoning, which is why
   L-SAN-001 is a guard against a call site appearing rather than a sanitiser
   over an empty path.

8. **BLS has returned 503 on every recorded cycle.** One of six macro
   families. This is why L-SRC-001 is release work and not speculation.

## The replay blocker, because it will look like a bug

`D-REP-002` is BLOCKED_DATA on a measured gate: `macro_retrieval_months 1/6`.

Every macro observation was retrieved inside ONE month (2026-08) while
describing periods across 2024–2026, so `vintage.freeze` admits **zero** rows
at any earlier instant and `select_episodes` returns `[]` on the live corpus.

**The shortcut is filtering on `published_at`, and it is the exact defect
D-REP-001 built the wall against.** It would admit 1572 unseen figures at
2026-01-01 and the replay would look entirely healthy. **Do not touch this
node.** The gate clears on its own as observation history accumulates. If
replay suddenly produces live episodes, check the wall still reads
observation time before believing it.

## Next action

Run `frontier.py`. Do not assume the order in this file still holds.

As of `cef65d3`: 49 nodes, COMPLETE 26, READY 8, WAITING_DEPENDENCY 9,
BLOCKED_DATA 4, NOT_APPLICABLE 2. Runtime pinned to `cef65d3`, PAPER
enforced, production `119d345` untouched.

`H-CEO-001` unblocks three others and is the highest-reach node left — and
the learning channels have said FOUNDER_VALUE = UNMEASURABLE for three
sessions running, which makes it the bottleneck the system itself is
pointing at. It needs the Founder repo and real DecisionImpact records;
publication counts are not decision value and the channel already refuses
them.

`L-ADV-001` and `L-SAN-001` are bounded and finishable on this branch.
`E-DEM-002` (demand-state contradiction handling) opened when E-DEM-001
closed, and the live corpus already produced one contradiction to work from.

**The governing lesson of the last two sessions, worth applying before any
new intelligence layer: prove the information survives the whole path into
canonical evidence BEFORE building the reasoning that consumes it.** Two
sessions running, the binding constraint was upstream representation loss,
not the reasoning at the end of the pipe.
