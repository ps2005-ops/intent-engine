# Collective Human State

*Contract: `collective_state.v1`. Package: `intent_engine.econ`.*

This document describes the collective-human subsystem: what it is, what it
refuses to do, and — most importantly — how little of it is currently
measurable. If you read only one section, read **The honest state of it**.

---

## 1. What this is

A probabilistic latent-state estimate over a **named population**, built from
**public behavioural evidence**, and typed **separately** from economic state.

It is not a model of anyone's mind. It is not a metaphysical claim. It is an
estimate of where a population sits on a small number of declared constructs,
carrying its own uncertainty, its own evidence, and its own record of the
evidence that disagreed with it.

```
CollectiveStateEstimate
  population          WHO / WHERE / WHICH COHORT / IN WHAT CONTEXT
  as_of               WHEN
  dimensions[]        one DimensionEstimate per construct
      posterior_mean  where in the construct's range this population sits
      uncertainty     a standard deviation on the same 0-1 scale
      confidence
      prior_mean      so `moved` is computable
      evidence[]
      contradictory_evidence[]     retained, never absorbed
      lag_model       typical / lower / upper days, with its basis
      promotion_state CANDIDATE .. PROMOTED / RETIRED
      model_version
  source_nodes[]
  visibility          PUBLIC, always, in the shared core
```

## 2. Why it is typed separately from economic state

Section 3 of the specification draws the line: **credit stress is not fear,
and market volatility is not anxiety.** They may turn out to be causally
linked — that is §18's question, answered by measurement — but they are
different objects estimated from different evidence.

The moment "fear" is allowed to be a synonym for "the VIX", the engine loses
the only interesting question it could ask: *did people know something the
aggregates had not yet shown?*

This is enforced, not documented:

- `BEHAVIORAL` is its own node class, and no kind appears in both `MACRO` and
  `BEHAVIORAL`.
- `vocabulary.collective_dimension_collisions()` must return empty, and
  `test_economic_and_collective_vocabularies_are_disjoint` computes the
  intersection **itself** rather than trusting that helper.

The first run of that guard found a real collision: `institutional_trust` had
been declared as both a measurement kind and a latent construct. The
measurement is now `trust_index`; the inference is `institutional_trust`.

## 3. Every estimate names a population

"The market is fearful" is not a state. It is a sentence with no subject.

Scales: `HOUSEHOLD`, `DEMOGRAPHIC_COHORT`, `CONSUMER_COHORT`, `WORKER_COHORT`,
`INVESTOR_COHORT`, `EXECUTIVE_COHORT`, `INDUSTRY`, `POPULATION`.

`INDIVIDUAL` is declared and **permanently refused** by the public core. An
individual's state is a Personal-AI object inside one tenant (§52), and the
enforcement is that `Population.__post_init__` raises rather than trusting a
caller not to ask.

Fear among first-time homebuyers, fear among hedge funds and fear among bank
risk officers are three different estimates supported by three different
bodies of evidence. `estimate_many` gives each population **its own** node
set; handing every population the same evidence would reproduce exactly the
failure this rule exists to prevent, with more objects.

## 4. The rendering rule is code

§5 forbids *"Americans are 73% afraid."* That prohibition cannot live in a
style guide, because the number is right there in the dataclass and the
sentence writes itself.

`collective.narrate()` is the only supported renderer. It says what the
evidence is **consistent with**, names the population, and carries the
uncertainty. `assert_renderable()` refuses the headcount sentence shape, and
`narrate` runs it on its own output.

> Available behavioural evidence is consistent with financial anxiety rising
> among first time homebuyers (under 35) in US, with moderate uncertainty.

A posterior over a construct is not the fraction of a population that feels
it, and nothing in this package will render it as one.

## 5. Arrival is not learning

Every observation batch produces a **named effect**, not just a posterior:

| effect | meaning |
|---|---|
| `CONFIRMATION` | the observation is where the prior expected it |
| `STRENGTHENING` | the reading is more pronounced than it was |
| `WEAKENING` | it is pulling back toward the midpoint |
| `CONTRADICTION` | it sits ≥2 posterior sd from the prior — surprising |
| `NO_INFORMATION` | nothing in this batch measures this construct |
| `DUPLICATE_EVIDENCE` | already folded in; re-reading it is arrival |

Only the first four count as informative. This exists because this codebase
has produced the number **554 units of learning for a cycle that learned three
things**, and a counter that cannot separate arrival from information will
produce it again.

Updates are precision-weighted (1/variance). A survey of 300 people and a
payments panel of 40 million do not move a posterior by the same amount, and
uncertainty can only shrink when evidence actually arrives.

Contradictory evidence is **retained** on the estimate. A posterior that has
quietly absorbed what disagreed with it cannot be audited.

## 6. A proxy is a hypothesis, not a definition

Each `Proxy` declares: the observation kind, the construct it loads on, the
sign, the expected range, the instrument noise, a **rationale**, and whether
it is `contested`.

Contested means the observation is consistent with more than one construct.
The motivating case is the saving rate: rising precautionary saving is
consistent with rising **financial anxiety** *and* with rising **perceived
control**. Both are defensible. So it is marked contested with a wide noise,
and a construct supported only by contested proxies gets its uncertainty
widened by `CONTESTED_WIDENING` — the honest encoding of "this evidence does
not discriminate", rather than picking one and claiming a precision it never
had.

Clamped readings (a value outside its declared range) get widened noise too. A
series that keeps pinning the top of its range means the range is wrong, and
silently saturating it would hide that.

## 7. The gate: incremental predictive value

**This is the only thing that may promote a construct.** It is the difference
between a psychological world model and astrology.

A collective-state layer will always produce plausible narrative. Every crisis
can be retold as fear, every bubble as greed, and the retelling will fit
because it was written afterwards. **Fitting is free.** So the layer gets no
credit for explaining anything.

```
MODEL A:  base economic model                       -> score X
MODEL B:  base economic model + collective state     -> score Y
DELTA  =  X - Y            (positive means B won; it is a loss)
```

Both models forecast the **same targets** from the **same cutoffs**. The only
difference is the collective feature. So the statistic is the per-target
difference in loss, and its sampling distribution comes from resampling those
paired differences — no distributional assumption, because forecast losses are
skewed and a t-test on them would overstate significance in exactly the
direction that flatters the new feature.

Four ways a comparison can fail to establish value:

| verdict | meaning |
|---|---|
| `INSUFFICIENT_SAMPLE` | fewer than 30 paired forecasts. Not a weak result — not a result |
| `NO_IMPROVEMENT` | the augmented model's mean loss is no better |
| `NOT_ROBUST` | positive point estimate, 95% interval includes zero |
| `IMPROVEMENT` | interval clear of zero — *and still pending FDR* |

Then Benjamini-Hochberg at q=0.10 across the **whole** family of tested
comparisons. Sixteen constructs × four regimes × three horizons is 192 tests;
at p<0.05 roughly ten look significant with no signal present at all. The
correction is applied to every tested comparison, not only the winners —
selecting the family after seeing which tests won is the error the correction
exists to prevent.

Hindsight is **refused, not scored**: every forecast's `information_cutoff`
must predate its outcome's `knowable_at`, and `Outcome` carries both
`occurred_at` and `published_at` because for revised series they differ.

## 8. A construct's life and death

```
CANDIDATE  -> OBSERVED -> TESTED -> REPLICATED -> PROMOTED
                  |          |          |            |
                  +----------+----------+------------+--> WEAKENED
                  +----------+----------+------------+--> RETIRED
```

- **OBSERVED** means a named proxy actually produced a posterior. The first
  cycle wiring seeded constructs at OBSERVED because a proxy was *declared*;
  that claimed a measurement that never happened, and was corrected.
- **REPLICATED** requires passing in **two distinct regimes**. Passing twice in
  the same regime is one finding observed twice.
- **PROMOTED** is the only state that may enter the causal graph, reach a
  founder surface, or corroborate a bleed.
- **RETIRED** is what makes this a scientific object rather than a taxonomy.
  Two clear failures with no passes and the construct is removed — and
  `estimator.estimate()` stops **computing** it, not merely hiding it.
  Filtering at the surface is not removal.
- **`revive()`** returns a retired construct to `CANDIDATE`, never to
  `PROMOTED`.

The asymmetry (two passes to promote, one clear failure to weaken) is
deliberate: a promoted construct starts informing decisions, while a retired
one costs only the effort of having tested it.

## 9. The honest state of it

**Sixteen constructs are declared. One is measurable today.**

| | count | which |
|---|---|---|
| declared | 16 | the full `COLLECTIVE_DIMENSIONS` vocabulary |
| have a proxy | 8 | anger, financial_anxiety, future_orientation, institutional_trust, perceived_control, risk_appetite, stress, time_horizon |
| **measurable now** | **1** | **perceived_control** |
| promoted | 0 | — |
| retired | 0 | — |

**Why only one.** The proxies exist; the *series* do not. `series.BEHAVIOURAL`
declares 16 behavioural series. Two are LIVE — BLS JOLTS quits and labour-force
participation, both genuinely keyless, both verified by calling the endpoint.
Six are KEYED behind FRED, whose API needs a key this deployment does not
have and whose keyless CSV endpoint did not answer within 12s when called.
Six more are UNAVAILABLE with stated reasons: trust barometers are proprietary
and annual, retail order flow is a vendor product, trends APIs forbid the
redistribution, and no public series measures basket substitution directly.

These were **first written as LIVE** because the underlying figures are public
and the series ids are real. Then the endpoints were actually called. The
correction from LIVE to KEYED is the difference between a coverage figure that
is true and one that merely looks better.

The single most damaging gap is **delinquency**. It is the discriminating
instrument for financial anxiety, and without it that construct rests on
contested proxies alone.

**What this means.** The architecture is complete and the data is the binding
constraint. That is a materially different situation from a modelling failure,
and it points at a different fix: an adapter or a key, not a better model.

## 10. Where it is wired

| surface | what it does |
|---|---|
| `market/behavioral_ingest.py` | fetches BLS behavioural series as `BEHAVIORAL` nodes, never `MACRO` |
| `market/steps.py::_econ_collective` | the cycle producer. Fetches, persists, estimates, transitions the register, re-stamps the estimate |
| `econ/dashboard.py` → `/learning-acceleration` | §49. Measured / usable / promoted, always together, plus why each construct cannot be measured |
| `econ/founder_view.py` | §50. Two gates: PROMOTED **and** a declared company channel |
| `econ/transmission.py` | §13/§14 chains, gated on PROMOTED |
| `econ/bleed.py` | §21/§22. Only a PROMOTED construct may corroborate |
| `econ/episodes.py` | §19/§20/§41 historical partitions |

## 11. What it refuses

- an individual's state, in the public core, always
- a posterior rendered as a fraction of a population
- a posterior with no evidence behind it
- an untested construct reaching any decision surface
- the same psychological conclusion dumped into every company
- a bleed blamed on something nobody can measure
- a construct promoted from one regime
- a comparison scored against an outcome its cutoff did not precede
- a fabricated behavioural series in place of one that cannot be read

## 12. Known limitations

1. **Calibration is `PRE_CALIBRATION` at n=0 real forward resolutions.** No
   collective construct has been tested against a real forward outcome. The
   closed-loop demonstration uses generated outcomes, which §39 forbids
   counting as market learning; it proves the machinery separates a wired
   signal from wired noise, and nothing about the real economy.
2. **One population.** Only `US_households` is estimated in production. The
   cohort machinery supports the rest and nothing produces them yet.
3. **Eight constructs have no proxy at all** and are permanently `CANDIDATE`
   until one is written.
4. **The lag model for `institutional_trust` is 90 days** and the 2023
   regional-bank episode is a three-day bank run. That construct's lag model
   cannot describe its own most important episode, and the episode says so.
5. **No transmission edge is above evidence level 1.** Every chain reads
   "ASSOCIATED WITH", never "causes". Raising them is what the historical
   programme is for.
