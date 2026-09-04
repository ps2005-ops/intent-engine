# The unified world model

*One closed loop, four state families, one package: `intent_engine.econ`.*

---

## 1. The architectural claim

There is **one** world model. Market Intelligence, Founder Intelligence,
Public Company Intelligence and the collective-human layer are surfaces onto
it, not parallel products.

The thing that makes this real rather than aspirational is a wall: the founder
package may not import the market package, and the market package may not
import the founder package. `tests/test_econ_core_is_neutral.py` parses every
module in `econ/` and refuses any import of either product's internals. So the
shared substrate is *structurally* incapable of reaching either side, and both
cross into a third package instead.

Unification is exactly the change that would have broken that wall, so the
wall is re-asserted rather than relaxed.

## 2. Four state families, kept apart on purpose

```
                         WORLD STATE
                             |
        +--------------------+--------------------+
        |                    |                    |
        v                    v                    v
 ECONOMIC STATE       COMPANY STATE        COLLECTIVE HUMAN STATE
   EconomicState    CompanyEconomicState   CollectiveStateEstimate
   econ/state.py      econ/company.py        econ/collective.py
        |                    |                    |
        +--------------+-----+--------------+-----+
                       |                    |
                       v                    v
                  INCENTIVES            PERCEPTION
                       |                    |
                       +----------+---------+
                                  |
                                  v
                              BEHAVIOUR
                       BEHAVIORAL node class
                                  |
                 +----------------+----------------+
                 |                |                |
                 v                v                v
              SPENDING        INVESTING        EMPLOYMENT
                 |                |                |
                 +----------------+----------------+
                                  |
                                  v
                          COLLECTIVE OUTCOME
                                  |
                  +---------------+---------------+
                  |                               |
                  v                               v
            ECONOMIC EFFECT                  MARKET EFFECT
                                                  |
                                     MarketParticipantState
                                        econ/levelk.py
                  +---------------+---------------+
                                  |
                                  v
                             NEW WORLD STATE
                                  |
                                  +----> learning loop
```

**They do not collapse into each other.** Credit stress is not fear. Market
volatility is not anxiety. A dealer's gamma is not a mood.

`CollectiveHumanState` covers households, consumers, workers, executives and
broad investor cohorts. `MarketParticipantState` covers dealers, CTAs, risk
parity, vol control and systematic flows. They interact — consumer fear →
spending down → retailer earnings down → analyst revisions → systematic factor
flows — but one is not the other, and they are estimated from different
evidence by different modules.

## 3. Five node classes

| class | what it measures | module |
|---|---|---|
| `MACRO` | the economy | 35 kinds |
| `MARKET_STRUCTURE` | prices, positioning, volatility | 13 kinds |
| `COMPANY` | one firm's operations | 22 kinds |
| `STRATEGIC` | competitive moves | 7 kinds |
| **`BEHAVIORAL`** | **what a population did or reported** | **26 kinds** |

`BEHAVIORAL` is deliberately a fifth class rather than a subset of `MACRO`.
A behavioural observation is a measurement *of people*, and the moment it is
filed as macro the engine loses the ability to ask whether people showed
something the aggregates had not. More concretely: if quits arrived as a macro
labour reading, the incremental-value comparison would be scoring a model
against itself.

No kind appears in two classes. No collective construct shares a name with an
economic quantity. Both are asserted by tests that compute the intersection
themselves.

## 4. The closed loop, and where each arrow lives

| step | module | status |
|---|---|---|
| observe world | `evidence`, `market/macro_ingest`, `market/behavioral_ingest` | live |
| estimate observable economic state | `econ/state.py` | live |
| infer collective human state | `econ/estimator.py` | live, 1 construct |
| update company operating states | `econ/company.py` | live |
| form / attack beliefs | `econ/belief.py`, `econ/attacks.py` | live |
| model causal-temporal structure | `econ/causal.py`, `econ/transmission.py` | live |
| detect reflexivity | `econ/reflexivity.py`, `econ/levelk.py` | live |
| identify causal bleeds | `econ/bleed.py` | built |
| choose information | `econ/voi.py` | live |
| preregister expectation | `econ/belief.py` | live |
| paper / no-trade decision | `econ/execution.py`, `econ/zero_trade.py` | live |
| resolve, calibrate, attribute | `econ/calibration.py`, `econ/replay.py` | live |
| **promote / weaken / retire** | `econ/promotion.py`, `econ/construct.py` | live |
| measure learning acceleration | `econ/acceleration.py` | live |
| publish sanitised state | `market/econ_bridge.py` | live |
| founder consumes it | `econ/founder_view.py` | live |

## 5. The two gates

Every path from a psychological construct to a decision passes through both.

**Gate 1 — did it earn its place?** (§18, §42)
The construct must be `PROMOTED`: it beat the base economic model on paired
out-of-sample forecasts, in two distinct regimes, with a bootstrap interval
clear of zero, surviving Benjamini-Hochberg at q=0.10 across the whole test
family, with no forecast scored against an outcome its cutoff did not precede.

**Gate 2 — does it reach this company?** (§13, §50)
The company must have a declared `Exposure`: a named channel and a named
company observable it would show up in. A company with no declared channel
gets **nothing** — not the population average.

Failing gate 1 is a research state. Failing gate 2 is a coverage state. They
call for opposite work — run an experiment, or map the company's exposures —
so `founder_view` reports them separately and names the *dominant* one.

## 6. Lineage and double counting

If company evidence contributes to a `ConsumerStressIndex`, the same report
cannot later treat that index as independent corroboration. Every derived
signal stores `lineage[]` and `depends_on[]`, and `econ/lineage.py` understands
derivation rather than comparing source labels.

This bites the collective layer specifically: company disclosure of customer
trade-down is real evidence, and it enters as `COMPANY` evidence. It may
therefore never corroborate a consumer aggregate built from the same
disclosures. `series.BEHAVIOURAL` records that as the reason `trade_down` has
no behavioural series rather than approximating one.

## 7. The privacy firewall

Public world model: **public evidence only.** Not filtered — *refused*. An
aggregate quietly built from private material and reported as smaller is a
breach that also lies about its own sample.

The collective layer adds one enforcement: the public core cannot construct an
`INDIVIDUAL`-scale population at all. §52's Personal AI will hold individual
and team state inside a tenant; the public core does not trust its callers not
to ask for one, it raises.

Zero cross-tenant learning by default.

## 8. What the model refuses to say

- causal language below evidence level 3 — the string is not constructed on
  that branch, so there is no flag that produces it
- an accuracy figure before the declared minimum forward sample
  (`PRE_CALIBRATION`)
- a posterior over a construct as a fraction of a population
- an untested construct informing any decision
- a derived signal as independent evidence of its own input
- live capital, at this stage, by construction

## 9. Known limitations of the world model as a whole

1. **`CALIBRATION_STATUS = PRE_CALIBRATION`**, n=0 forward resolutions for the
   collective layer. Nothing here has an accuracy claim.
2. **No transmission edge is above level 1.** Every chain reads "ASSOCIATED
   WITH". Raising them needs the historical programme, which needs vintage
   history this deployment cannot read.
3. **One population, one measurable construct.** See
   [`BUILD_STATUS.md`](BUILD_STATUS.md).
4. **The market engine's own cycle path still reads headlines** through its
   ledger-shaped exposure reader. The shared exposure capability is used by
   the founder path, not yet by that one.
5. **§9's state-space engine is partial**: precision-weighted Bayesian updating
   with uncertainty, but no dynamic transition model. A construct's posterior
   does not decay toward a prior between observations.


---

## The dimension ledger, and why LIVE is not the same as useful

*Added at V3 closure. `reports/v3_closure.json` holds the derived ledger;
`scripts/close_v3.py` produces it from canonical records.*

A dimension can be LIVE and useless. LIVE counts a series being readable,
which is a fact about acquisition rather than about value: a dimension
nothing consumes and nothing decides on is infrastructure, and reporting it
beside a decision-relevant one inflates coverage with things that do not
matter.

Four states, assigned by `worldmodel.classify_dimension`:

| state | meaning |
|---|---|
| `LIVE_DECISION_RELEVANT` | a company consumes it AND it has produced a delta |
| `LIVE_CONTEXT_ONLY` | consumed, or supporting a relation, but deciding nothing yet |
| `LIVE_UNPROVEN_VALUE` | readable and reaching nothing |
| `BLOCKED` | no series in this panel measures it |

The blocked dimensions **stay in the denominator**. Removing them would raise
coverage by narrowing the question, which is the failure the four states
exist to prevent.

## Relations: a lag that has not elapsed is not a failure

`RelationCheck.state` orders its tests deliberately. A relation whose regime
does not hold, or whose driver did not move, is CANDIDATE — untested, not
failed. One whose driver moved but whose lag has not elapsed is PENDING_LAG.
Only after the lag has elapsed does the target's behaviour decide between
SUPPORTED_PREDICTIVE, OBSERVED, CANDIDATE_NOT_PROVEN and CONTRADICTED.

An earlier bleed detector compared year-on-year changes with no lag check at
all and reported four of six relations as non-firing — some of which had
simply not had time to fire.

The ledger records `next_eligible_evaluation` per relation, computed from the
lag, so a later cycle does not re-report the same untested relation as a
failure.

## The transmission tables

Two tables, one key: `(channel, business_model_class)`.

- `_TRANSMISSION` gives the mechanism — the sentence saying HOW the condition
  reaches this kind of business.
- `_ADVERSE_DIRECTION` gives the sign — which way it has to move to hurt.

Sharing the key is what stops them disagreeing. A pair present in the first
and absent from the second has a mechanism and **no established sign**, and
that is deliberate: several mechanisms state both directions ("many contracts
and tariffs escalate with inflation, so it reaches revenue as well as cost"),
and asserting a net effect the evidence does not carry is the failure the
absence prevents.

`CURVE_SLOPE` and `CREDIT_SPREAD` are separate channels from `MARKET_RATE`
because neither is the LEVEL of rates. Folding all three together gave a bank
three exposures through one channel whose sign is deliberately unestablished,
so it could never receive an economic reading at all — which is the clearest
case there is of a condition reaching a business through a named mechanism.
