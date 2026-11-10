# The collective-human layer: final report

*§63's report, answered field by field. Branch `v6/unified`.*

---

## The short version

The world model now holds **Collective Human State as a first-class typed
subsystem** alongside economic, company and market-participant state — not as
a later Personal-AI concern. It is gated on **out-of-sample incremental
predictive value**, and the gate has been demonstrated to retire a construct
that predicts nothing.

Nine new modules, 41 of 41 deliberate defects caught by named tests, and the
closed loop runs twice showing behaviour changed because it learned.

**One of sixteen constructs is measurable with data this deployment can read,
and `CALIBRATION_STATUS = PRE_CALIBRATION` at n=0 real forward resolutions.**
The binding constraint is data acquisition, not modelling.

---

## §63 report

```
REPOSITORY_SOURCE_OF_TRUTH   = docs/architecture/{CANONICAL_SYSTEM,
                               WORLD_MODEL, COLLECTIVE_STATE_MODEL,
                               DATA_LINEAGE, BUILD_STATUS}.md
                               docs/validation/COLLECTIVE_STATE_RESEARCH.md
                               docs/roadmap/V3_V5_MASTER_PLAN.md
                               Chat history is not required to understand it.

ECONOMIC_STATE               = econ/state.py — LIVE (unchanged this tranche)
COMPANY_ECONOMIC_STATE       = econ/company.py — LIVE; gained
                               `collective_exposures`

COLLECTIVE_HUMAN_STATE       = econ/collective.py — LIVE. Typed separately;
                               vocabularies asserted disjoint
COHORT_MODEL                 = 8 scales declared, INDIVIDUAL refused in the
                               public core. 1 population estimated in
                               production (US_households)
COLLECTIVE_STATE_PROXIES     = 19 declared, each with a rationale, sign,
                               range, noise and a `contested` flag.
                               8 of 16 constructs have a proxy
LATENT_STATE_UNCERTAINTY     = posterior + uncertainty + confidence on every
                               dimension; contested-only support widens it;
                               clamped readings widen it further

MARKET_PARTICIPANT_STATE     = econ/levelk.py — LIVE. Kept typed apart from
                               collective state; §29 asserted by test, which
                               found and fixed a real spelling drift
                               (corporate_buyback vs corporate_buybacks)

BAYESIAN_UPDATE              = econ/bayes.py — precision-weighted, with a
                               NAMED effect per batch. Arrival is not learning
CAUSAL_TEMPORAL_GRAPH        = econ/causal.py + econ/transmission.py
CAUSAL_EVIDENCE_LADDER       = 6 rungs. Causal language floor at L3, enforced
                               by not constructing the string below it

PSYCHOLOGY_ECONOMY_EDGES     = 7 links across 3 chains
ECONOMY_PSYCHOLOGY_EDGES     = 5 links across 2 chains
REFLEXIVITY                  = 2008 upswing and downswing as SEPARATE chains,
                               so confirming one cannot carry the other

TRAJECTORY_ENGINE            = NOT BUILT as a typed object. The comparison
                               §23 exists for is performed by bleed.detect;
                               a typed trajectory with no producer would be
                               a vertical §59 forbids. See BUILD_STATUS
                               "Deliberately not built this tranche"
CAUSAL_BLEEDS                = econ/bleed.py — BUILT. Only a PROMOTED
                               construct may corroborate one
COUNTERFACTUAL               = pre-existing
EVSI                         = econ/voi.py — LIVE (unchanged)

BELIEF_LEDGER                = econ/belief.py — LIVE, append-only
EXPECTATION_LEDGER           = econ/belief.py — LIVE, append-only
CALIBRATION                  = econ/calibration.py — LIVE

IMPOSSIBLE_HYPOTHESIS        = econ/attacks.py — LIVE
LEVEL_K                      = econ/levelk.py — LIVE

PAPER_EXECUTION              = econ/execution.py — LIVE, live capital refused
ZERO_TRADE_LEARNING          = econ/zero_trade.py — LIVE

COLLECTIVE_STATE_BASELINE_SCORE = NOT MEASURED
ECONOMIC_PLUS_COLLECTIVE_SCORE  = NOT MEASURED
INCREMENTAL_DELTA               = NOT MEASURED  (reported as None, never 0.0)

COLLECTIVE_VARIABLES_PROMOTED   = 0 in production
COLLECTIVE_VARIABLES_RETIRED    = 0 in production
                                  (1 promoted, 1 retired in the controlled
                                   closed-loop demonstration)

LEARNING_ACCELERATION        = econ/acceleration.py — LIVE; collective
                               updates feed it before it is computed

COMPANY_TO_MARKET            = econ/aggregates.py — LIVE
MARKET_TO_COMPANY            = econ/founder_view.py — LIVE
HUMAN_TO_COMPANY             = econ/transmission.py — 10 exposures across 8
                               companies, each naming its own channel

DOUBLE_COUNTING_WALL         = econ/lineage.py — LIVE. It is why `trade_down`
                               is declared UNAVAILABLE rather than built from
                               the retailer commentary that describes it
PRIVATE_DATA_FIREWALL        = refusal not filtering; plus the public core
                               cannot construct an INDIVIDUAL population

VINTAGE_REPLAY               = econ/replay.py — LIVE
HISTORY_REWIND               = pre-existing founder surface

REAL_FORWARD_RESOLUTIONS     = 0
CALIBRATION_STATUS           = PRE_CALIBRATION

LIVE_LEARNING_CYCLES         = 3 collective cycles inspected end to end
SECOND_ITERATION_PROOF       = YES — behaviour changed (see below)

KNOWN_SEV1                   = 0
KNOWN_LEARNING_SEV2          = 1 — no behavioural series can currently be
                               read live (BLS quota spent; FRED needs a key),
                               so the gate cannot run on anything real

MARKET_WORLD_MODEL_FROZEN    = NO. Frozen requires a forward record
READY_FOR_CONTINUOUS_FORWARD_LEARNING = ARCHITECTURALLY YES, DATA-BLOCKED
```

---

## What was built

Nine modules in `intent_engine.econ`, plus one market adapter:

| module | what it is |
|---|---|
| `collective.py` | `CollectiveStateEstimate`. `narrate()` is the only supported renderer and refuses the headcount sentence |
| `proxies.py` | 19 observation→construct loadings, each a stated hypothesis with a rationale and an honest noise |
| `bayes.py` | precision-weighted posteriors, and a NAME for what each batch did |
| `estimator.py` | the cycle producer. Retired constructs are not computed |
| `incremental.py` | **the gate.** Paired, bootstrapped, FDR-corrected, hindsight-walled |
| `construct.py` | a construct's life and death, including real removal |
| `transmission.py` / `transmission_seed.py` | 8 chains both directions, 10 per-company exposures |
| `bleed.py` | where a mechanism under-delivered and what may have absorbed it |
| `episodes.py` | 9 historical regimes, train/validation/holdout fixed in source |
| `dashboard.py` / `founder_view.py` | §49 and §50 |
| `market/behavioral_ingest.py` | BLS JOLTS quits + participation as `BEHAVIORAL` nodes |

---

## Defects found by running it

Each of these was found by executing the thing, not by reading it.

**1. `institutional_trust` was both a measurement and an inference.**
The very first run of the disjointness guard found the collision. A trust
survey reading and an inferred latent trust state are different objects; the
measurement is now `trust_index`.

**2. Six behavioural series were declared LIVE and are not.**
They were written as LIVE because the figures are public and the series ids
are real. Then the endpoints were called: BLS answers, FRED's keyless CSV
endpoint did not answer within 12s, and `macro_ingest` already recorded that
the FRED API needs a key this deployment does not hold. Corrected to KEYED
with reasons. **This moved `dimensions_measurable_now` from 2 to 1.**

**3. The register seeded constructs as OBSERVED when nothing was observed.**
`observe()` means a named proxy produced a posterior. The wiring claimed it
because a proxy was *declared*. Constructs now seed at `CANDIDATE` and a
separate transition moves them only once a real posterior exists.

**4. One run said two things.**
The first cycle published a reading labelled `CANDIDATE` beside a register
that called the same construct `OBSERVED`, because the promotion transition
ran after the estimate was built. The estimate is now re-stamped from the
post-transition register before either is persisted.

**5. The founder brief named the wrong blocker.**
A company blocked by two missing channels and one untested construct was told
its problem was research. It is coverage. Those call for opposite work — run
an experiment, or map the company's exposures — so the empty-reason now names
the *dominant* gate and reports the others.

**6. The partition guard fired on the only measurable construct.**
`perceived_control` was testable only inside the holdout, so testing it at all
would have consumed the holdout. It was added to a training and a validation
episode. The holdout is intact.

**7. Two spellings of one market participant.**
The §29 test found `levelk` models `corporate_buybacks` while the shared
vocabulary declared `corporate_buyback`. Two spellings of one participant is
how a reflexive loop goes undetected. Aligned to the engine.

**8. Seven weak tests of my own.**
The break proof named them and each was replaced — see below.

---

## Break proof: 41 of 41

| suite | mutations | caught | NOT_CAUGHT | no-op |
|---|---|---|---|---|
| collective state | 22 | **22** | 0 | 0 |
| programme surfaces | 19 | **19** | 0 | 0 |

Mutations are applied to a **copy** of the tree; the shared worktree is never
written. A no-op (anchor missing) fails the run rather than passing silently.

The first pass returned **five NOT_CAUGHT**, and every one named a weak test
of mine rather than a missing guard:

1. an assertion inside `if verdict == NOT_ROBUST:` — a test that cannot fail
   when the branch does not fire. Replaced with a deterministic fixture.
2. the FDR test used pure-noise episodes whose verdicts were
   `NO_IMPROVEMENT` anyway, so disabling the correction changed nothing. It
   was checking the verdict, not the correction.
3. the promotion test used a CANDIDATE with zero regimes, which the regime
   count refuses anyway. Replaced with a construct the state check alone can
   refuse.
4. the disjointness test asserted the *helper* returned empty — which a
   helper hardcoded to return empty also satisfies. Now computes the
   intersection itself.
5. the proxy test read a fully-populated registry, so deleting the
   requirement left it green. Now exercises the constructor.

A second pass found two more of the same shape, plus one guard that could not
be shown to fire at all: `assert_partition_discipline` could only run against
the production episode list, which satisfies it by construction. It now takes
an episode set so the suite can pass a violating one as a positive control.

---

## §57: did behaviour change because it learned?

`scripts/collective_closed_loop.py`, two iterations, one construct wired to
carry signal and one wired to carry none:

```
  anger                OBSERVED     -> RETIRED
  financial_anxiety    OBSERVED     -> PROMOTED
  transmission chains open      0 -> 3
  WMT readings shown            0 -> 1
  delta measured                0.00695 -> 0.00674

  VERDICT: SYSTEM BEHAVIOUR CHANGED BECAUSE IT LEARNED
```

The bleed went `CANDIDATE_NAMED` → `CORROBORATED` in iteration 2, because the
construct became PROMOTED *and* moved the way the account requires.

**What this does not establish.** The outcomes are generated. §39 forbids
counting a synthetic trajectory as market learning, and the script says so in
its own output. What it proves is that the machinery separates a wired signal
from wired noise and that the consequence propagates all the way to what a CEO
is allowed to be told. Whether any real construct carries signal is a question
only forward resolutions can answer.

Two things worth reading correctly. The delta barely moves between iterations
(0.00695 → 0.00674) and the second is *lower* — the aggregate averages the
noise construct in alongside the signal one, so it is not a progress bar and
should not be read as one. **The state transitions are the finding**, not the
delta drift.

And the script had a reproducibility defect of its own: it seeded from
Python's built-in `hash()`, which is randomised per interpreter by
`PYTHONHASHSEED`, so it produced different figures on every run while looking
seeded. It now uses a stable SHA-256 digest and two consecutive runs return
identical numbers. §55 requires every learning metric to be reproducible, and
a demonstration whose figures move each time is not one.

---

## Three cycles of the live producer

| cycle | evidence | effect | reading |
|---|---|---|---|
| 1 | quits 2.4, participation 62.8 | `STRENGTHENING` | perceived control at an elevated level |
| 2 | **identical rows** | `DUPLICATE_EVIDENCE` | 0 informative, 1 arrived without informing |
| 3 | new month, quits 1.6 | `CONTRADICTION` | perceived control **deteriorating**, moved −0.20 |

Cycle 2 is the point. A counter that measured rows appended would have
reported learning; this one reports that nothing was learned.

---

## Three things I want stated plainly

**Calibration is `PRE_CALIBRATION` at n=0.** No collective construct has faced
a real forward outcome. There is no accuracy claim of any kind here, and the
code refuses to make one.

**One construct of sixteen is measurable.** Eight have no proxy at all; seven
have proxies whose series need a key this deployment does not hold or do not
exist publicly. The layer is built, wired, guarded — and starved. A FRED API
key would move six constructs, including `financial_anxiety`, which every
transmission chain in the seed depends on. That is the single highest-value
action available and it is not a research programme.

**No transmission edge is above evidence level 1.** Every chain reads
"ASSOCIATED WITH", never "causes". Seeding them at level 3 so the prose read
better would have been the most damaging single thing in this work — it would
have put unearned causal language on a founder surface and made the entire
evidence ladder decorative.
