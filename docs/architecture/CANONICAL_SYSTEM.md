# The canonical system

*One repository, one world model, several surfaces. Start here.*

This is the index §2 asks for: enough that someone who cloned this repository
tomorrow, with no chat history and no local-only files, could reconstruct what
the system is and what state it is in.

---

## The one-paragraph version

`intent_engine.econ` is a neutral substrate that imports neither product. It
holds the canonical `EconomicState`, `CompanyEconomicState` and
`CollectiveStateEstimate`, the causal-temporal graph and its evidence ladder,
the belief and expectation ledgers, calibration, lineage, the privacy
firewall, paper-execution realism, zero-trade learning, and the promotion
machinery that decides what counts as knowledge. Market Intelligence and
Founder Intelligence are surfaces onto it. Neither may import the other, and a
parsing test enforces that forever.

## Documents

| document | what it answers |
|---|---|
| [`WORLD_MODEL.md`](WORLD_MODEL.md) | the four state families, the closed loop, the two gates, what the model refuses to say |
| [`COLLECTIVE_STATE_MODEL.md`](COLLECTIVE_STATE_MODEL.md) | the collective-human subsystem in full, including **how little of it is measurable today** |
| [`BUILD_STATUS.md`](BUILD_STATUS.md) | every capability, tagged `LIVE_PROVEN` / `BLOCKED_DATA` / … |
| [`DATA_LINEAGE.md`](DATA_LINEAGE.md) | where every number comes from and what may corroborate what |
| [`../validation/COLLECTIVE_STATE_RESEARCH.md`](../validation/COLLECTIVE_STATE_RESEARCH.md) | the incremental-value experiment, the episode partition, and the current (null) results |
| [`../econ/FINAL_REPORT.md`](../econ/FINAL_REPORT.md) | the economic core's own build record and its three live market cycles |

## The package

```
intent_engine/econ/                     24 + 9 modules
├── vocabulary.py      the words both products must agree on. Imports nothing
├── evidence.py        EconomicNode, Provenance, EvidenceGraph
├── state.py           EconomicState        — the canonical public object
├── company.py         CompanyEconomicState — one company in that economy
├── series.py          what is readable, what is keyed, what does not exist
├── causal.py          the graph and the 6-rung evidence ladder
├── belief.py          beliefs and preregistered expectations, append-only
├── calibration.py     forward scoring; PRE_CALIBRATION until earned
├── replay.py          vintage-correct replay with a four-way verdict
├── lineage.py         a derived signal may not corroborate its own input
├── promotion.py       candidate -> knowledge, with overfitting defences
├── acceleration.py    is it learning faster, and is it learning as well
├── voi.py             what to find out next, bounded
├── levelk.py          market participants and their level-k responses
├── reflexivity.py     belief -> positioning -> price -> forced flow -> belief
├── shock.py           structural shock propagation
├── attacks.py         belief attack / impossible hypotheses
├── execution.py       paper fills with real friction; live refuses
├── zero_trade.py      learning from what was declined
├── aggregates.py      company evidence -> macro aggregate candidates
├── exposure.py        macro exposure extraction from documents
├── store.py           append-only durable form
├── seed.py            the seeded graph
│
│   ── the collective-human layer ──
├── collective.py      CollectiveStateEstimate; narrate() is the only renderer
├── proxies.py         observation -> construct, each loading a stated hypothesis
├── bayes.py           precision-weighted posteriors + what the evidence DID
├── estimator.py       the producer the cycle calls
├── incremental.py     THE GATE: base vs base+collective, paired, FDR-corrected
├── construct.py       a construct's life and death, including RETIRED
├── transmission.py    economy <-> psychology <-> behaviour <-> company
├── transmission_seed.py   the declared chains, at honest evidence levels
├── bleed.py           where a mechanism under-delivered, and what absorbed it
├── episodes.py        9 historical regimes, train/validation/holdout fixed
├── dashboard.py       the §49 payload
└── founder_view.py    the §50 gate: PROMOTED **and** a declared channel
```

## Where the surfaces are

| surface | path |
|---|---|
| market cycle producer | `market/steps.py::econ_publish_step` → `_econ_collective`, `_econ_acceleration`, `_econ_shocks`, `_econ_zero_trade` |
| behavioural acquisition | `market/behavioral_ingest.py` |
| economic acquisition | `market/macro_ingest.py` |
| state publication bridge | `market/econ_bridge.py` |
| learning dashboard | `webapp/app.py::_learning_acceleration` → `_collective_block` |
| founder brief | `econ/founder_view.py`, consumed by the founder step pages |

## The walls, and how each is enforced

| wall | enforcement |
|---|---|
| founder ⇄ market | `test_econ_core_is_neutral.py` **parses** every econ module and refuses any import of either product. It parses rather than greps because a grep matches the docstring explaining the rule |
| public ⇄ tenant-private | `PrivacyViolation` raised, never filtered. An aggregate quietly built from private material and reported as smaller is a breach that also lies about its own sample |
| public core ⇄ individual state | `Population.__post_init__` refuses `INDIVIDUAL` scale outright |
| derived ⇄ independent | `lineage.assert_not_self_corroborating` understands derivation |
| association ⇄ causation | below evidence level 3 the word "causes" is **not constructed on that branch** |
| measured ⇄ promoted | `founder_view` requires `PROMOTED`; `transmission.chains(enforce=True)` requires it; `bleed.corroborate` requires it |
| paper ⇄ live capital | `execution` refuses live, by construction |

## Reproducing the state of things

```bash
./.venv/bin/python -m pytest tests/ -q
```

```bash
# the closed loop, run twice, showing behaviour changed
./.venv/bin/python scripts/collective_closed_loop.py
```

```bash
# what is actually measurable
./.venv/bin/python -c "
from intent_engine.econ import series
import json; print(json.dumps(series.behavioural_coverage(), indent=2))"
```

## The honest headline

The world model is one closed loop and the collective-human layer is a
first-class typed subsystem inside it, gated on out-of-sample incremental
value. Every vertical is complete from producer to persistence to consumer to
UI to failure semantics, and the gate has been shown to retire a construct
that predicts nothing.

**One of sixteen constructs is measurable with data this deployment can read,
and `CALIBRATION_STATUS` is `PRE_CALIBRATION` at n=0 real forward
resolutions.** The binding constraint is data acquisition. Everything else is
built and waiting on it.


---

## The economic seam, end to end

*Added at V3 closure. This is the whole path from a published series to a
sentence a chief executive reads.*

```
reports/panel/historical_panel.jsonl        public, revision-aware
    -> scripts/publish_econ_state.py        the producer, year-on-year priors
    -> data/econ/state_snapshot.jsonl       the shared state, on disk
    -> econ.state.EconomicState             validated against an allowlist
    -> external_intel.econ_context          readings, re-validated on the way in
    -> external_intel.econ_decision         state x exposure x mechanism
    -> econ.founder_contract                FounderEconomicContext
    -> founder_brief.dossier                the ECONOMIC IMPACT passage
       founder_brief.qa                      the CEO answers
       webapp.app                            one memoised object per request
```

### The import wall

`econ` imports neither product. `tests/test_econ_core_is_neutral.py` parses
the source and refuses an import of `market`, `external_intel`,
`founder_brief`, `webapp` or any other product package. The founder side
consumes the neutral contract; the neutral core never learns a founder
exists.

### The four rules the seam rests on

**No evidenced exposure, no reading.** An exposure comes from the company's
own filings, and a condition it has no evidenced exposure to is named as
unmeasured rather than dropped — "this company is exposed to real yields and
nothing here measures them" is an information priority.

**No mechanism, no change.** The mechanism comes from
`company_profile._TRANSMISSION`, keyed on (channel, business model). A
condition with no mechanism into this business is reported and can never move
a decision.

**The sign is a company fact.** `_ADVERSE_DIRECTION` uses the same key as the
mechanism, so the two cannot disagree. A pair whose mechanism states BOTH
directions carries no sign, and that absence is deliberate: rising inflation
widens a scale retailer's everyday-low-price advantage and squeezes a
regulated provider whose net price is set by payers.

**A stale state cannot speak.** The context recomputes its own freshness from
the two dates it carries and refuses a producer whose label disagrees.

### One object, three surfaces

`FounderEconomicContext` is built once per request and memoised on the
per-request thread-local, cleared at the top of `_route` beside the other
memos — a memo that survives a request is the previous visitor's company.
"Brief and full may not contradict" is therefore a property of there being
one object, not of three renderers agreeing.

### Where the classification comes from, and what it gates

One classification per run, from `company_profile.profile_for`, gating four
things: the pattern library, the tension library, the transmission mechanism
and the adverse direction. A second copy is exactly how two parts of one run
came to disagree about what kind of business the subject is.
