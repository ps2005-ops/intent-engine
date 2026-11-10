# V4 EXTERNAL ECONOMIC FOUNDATION — FROZEN

    STATUS      COMPLETE_AND_LIVE_VERIFIED
    MARKET      766e15a1670fb28f49d4306ccdc71e11af87cc98
    FOUNDER     66ce3eb
    PRODUCTION  119d345, untouched
    MODE        PAPER, enforced
    FROZEN      2026-08-10

Do not reopen this contract absent a SEV-0 or SEV-1 regression. The remaining
BLOCKED_DATA nodes are terminal for themselves and clear on their own
measurements; they are not work.

## The outstanding proof, and what it showed

The last session corrected the stagnation check and could not sign the freeze
because no cycle had run from the corrected SHA. That cycle has now run.

    run_id                 2026-08-10:night:America/Toronto
    started                2026-08-10T19:49:32Z
    runtime_git_sha        766e15a1670fb28f49d4306ccdc71e11af87cc98
    dry_run                false
    exit                   0

`knowledge.stagnation`, from the persisted artifact:

    EVIDENCE_WITHOUT_EFFECT   16 of 417 (3.8%) against a floor of 5%   FIRING

    checks 5    FIRING 1    UNMEASURABLE 4    CLEAR 0

Both figures are counts of evidence rows, so the ratio is a share of a
population rather than a rate of one thing per another. The formulation it
replaced divided 442 effects by 416 evidence rows, reported 106%, and returned
CLEAR — an all-clear the arithmetic could never have failed to produce, because
one evidence row routinely produces several effects and the quotient could not
fall below a floor expressed as a share.

The alert can report both states. `test_market_stagnation.py` asserts CLEAR on
a healthy corpus; the live run shows FIRING; four checks show UNMEASURABLE,
which is neither and is reported as neither.

## runtime_tree_dirty

`runtime_provenance` recorded `runtime_tree_dirty: true` for this run. The
cause is one file:

    M reports/funnel_history.json

a report artifact the cycle itself writes. `git status --porcelain -- src tests
pyproject.toml` was empty immediately before launch and immediately after exit.
No file under `src/` was touched between them: the V5 work in flight during the
cycle was in a separate worktree, and only `docs/` was edited there.

This is recorded rather than waved past because the dirty flag is captured at
IMPORT and is blind to the working tree changing under a running process. It is
evidence of nothing on its own. What makes this run clean is the src/ status
either side of it, which is a different measurement.

## Non-regression, from the same artifact

    demand_chain           27 companies, 23 of 270 states measured,
                           1 contradicted link named
    source health          BLS refused on daily quota; reported as a named
                           failure under research.macro.failures, not as an
                           absence of activity. 2344 macro rows fetched, 0
                           errors across 28 companies.
    learning_acceleration  channels reporting with real denominators;
                           FOUNDER_UTILITY_GAIN UNMEASURABLE with its reason,
                           not zero
    adversary              48 cases, all SPECULATIVE, 0 actionable
    thesis transport       16 compared, 23 prior revisions loaded from disk,
                           0 identity collisions, 16 duplicate snapshots refused
    presentation           every deck carries alternatives
    CEO consumption        founder_v4: 16 views, all PROPOSED, all carrying
                           alternatives and a watch item
    learning_health        alerts: []
    knowledge_retention    0 objects lost
    tenant authority       does not exist in V4. It is V5 node F-TS-001, and
                           there is nothing here to regress.

## Terminal gates, preserved

Measured at the freeze. They are counters and they move: `prospective_decisions`
read 35 within hours, because the cycle that proved the freeze also added to it.
Read them from `metrics.py`, never from here.

    H-IMP-001   comparable_founder_revision_pairs   0 / 1
    C-MET-003   macro_retrieval_months              1 / 6
    D-REP-002   macro_retrieval_months              1 / 6
    B-HACK-001  prospective_decisions              32 / 100
    B-POL-002   prospective_decisions             32 / 100
    B-VOI-002   prospective_decisions             32 / 50

Each clears on its own measurement as the cycle keeps running. None of them may
be cleared by backfilling prospective rows, by manufacturing a Founder
revision, or by reading `published_at` as `retrieved_at`.

V5 node E-LDR-001 writes a second revision of a decision record, which is the
event that clears H-IMP-001's empirical half. That is a consequence of building
the Living Decision Record, not a reason to build it.

## Found during freeze verification, not fixed

`python -m intent_engine.market runs` defaults `--root` to `data`, while the
launchd jobs pass `--root /Users/prathamsharma/intent-engine-market`. An
operator running the command by hand from the repository root reads a stale
three-record store in `data/status/` and sees a world three days old, with
nothing indicating the file is not the live one. Production is unaffected —
launchd is explicit. Filed to BACKLOG as operator ergonomics; it is category F
under the execution constitution and does not extend the release frontier.
